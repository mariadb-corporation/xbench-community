import json
import logging
from typing import Dict, List, Optional, Tuple, Union
from urllib.parse import urljoin

import requests
from dacite import from_dict
from requests.exceptions import ConnectionError, ReadTimeout

from common import backoff_with_jitter, constant_delay, local_ip_addr, retry

from .exceptions2 import (
    SkySQLAPIClientException,
    SkySQLAPIException,
    SkySQLAPIServerException,
    SkySQLServiceFailed,
    SkySQLServicePending,
)
from .skysql2_data_model import Credentials, Service, ServiceId, ServiceState

SERVICES = "/provisioning/v1/services"
VERSIONS = "/provisioning/v1/versions"
RELEASES = "/provisioning/v1/releases"
PROJECTS = "/organization/v1/projects"

DEFAULT_API_TIMEOUT = 10
MAX_SERVICE_NAME_LENGTH = 24


class SkySQLAPI2:
    """Implements SKYSQL API V1
    (this is V2 actually you can find V1 inside skysql_api.py )
    https://api.mariadb.com/public/services/dps/docs/swagger/index.html

    Yet another valuable source is
    https://github.com/mariadb-corporation/cloud-automation/blob/6616ae9/moe/moe/cloud/aws/util.py#L57

    """

    clustered: bool = True

    def __init__(self, **kwargs):
        self.api_key = None
        self._bearer_token = None
        self.project_id = None

        self.region = None
        self.provider = None

        self.api_gw = None
        self.auth_url = None
        self.timeout = DEFAULT_API_TIMEOUT

        # Update instance variables from kwargs
        allowed_keys = list(self.__dict__.keys())
        self.__dict__.update(
            (key, value) for key, value in kwargs.items() if key in allowed_keys
        )

        self.logger = logging.getLogger(__name__)
        self.get_bearer_token()
        self.set_default_project_id()

    @property
    def auth_headers(self):
        """Default headers for making  REST API calls."""

        return {
            "Authorization": "Bearer " + (self._bearer_token or self.api_key),
            "Content-Type": "application/json",
        }

    @staticmethod
    def is_json_response(r: requests.Response) -> bool:
        """Return True if response has json data in it"""
        return True if "json" in r.headers.get("Content-Type", "") else False

    def check_status_code(self, r: requests.Response) -> None:
        """Check response for errors. Raise an exception if last call failed

        Args:
            r (requests.Response):

        Raises:
            SkySQLAPIClientException:
            SkySQLAPIServerException:

        {"errors":[{"error":"ERR_INVALID_OBJECT","message":"service is in pending delete state","type":"error"}],"exception":"ValidationException","path":"/provisioning/v1/services/:service_id/security/allowlist","code":400,"timestamp":1670368739186,"trace_id":"7758be6b6f63587e-IAD-r228dwpnkmcjxxw"}
        """
        if r.status_code < 300:  # 200, 201 are OK
            return
        else:
            self.logger.debug(r)
            if self.is_json_response(r):
                res = r.json()
                message = f'http error: {r.status_code} url: {self.url} error: {res.get("errors")[0].get("message")}'
            else:
                message = (
                    f"http error: {r.status_code} url: {self.url}, reason: {r.reason}"
                )

            if 400 <= r.status_code < 500:
                raise SkySQLAPIClientException(message)

            elif r.status_code >= 500:
                raise SkySQLAPIServerException(message)

    def autocomplete_url(self, url: str) -> str:
        """Convert relative url into absolute by adding a proper API gateway"""
        self.url = url if url.startswith("http") else urljoin(self.api_gw, url)
        return self.url

    # @retry(exceptions_to_check=(IncompleteRead, ReadTimeoutError, ReadTimeout, ConnectionError),
    # #       exception_to_raise=RestClientException, max_delay=300,
    #        delays=backoff_with_jitter(delay=3, attempts=10, cap=15))

    # def

    def post_only(self, url, data=None, headers={}) -> None:
        """I am not interested in results"""
        self._api_call(url=url, method="post", data=data, headers=headers)

    def post(self, url, data=None, headers={}) -> Dict:
        """POST and get the record back"""
        r = self._api_call(url=url, method="post", data=data, headers=headers)
        if isinstance(r, Dict):
            return r
        else:
            raise SkySQLAPIException(f"POST to {url} should return dict")

    def delete(self, url, params=None, headers={}) -> None:
        r = self._api_call(url=url, method="delete", params=params, headers=headers)

    def get_one(self, url, params=None, headers={}) -> Dict:
        r = self._api_call(url=url, method="get", params=params, headers=headers)
        if isinstance(r, Dict):
            return r
        else:
            raise SkySQLAPIException(f"Get to {url} should return Dict")

    def get(self, url, params=None, headers={}) -> List:
        r = self._api_call(url=url, method="get", params=params, headers=headers)
        if isinstance(r, List):
            return r
        else:
            raise SkySQLAPIException(f"Get to {url} should return list")

    @retry(
        exceptions_to_check=(ReadTimeout, ConnectionError),
        exception_to_raise=SkySQLAPIException,
        max_delay=300,
        delays=backoff_with_jitter(delay=3, attempts=10, cap=15),
    )
    def _api_call(
        self,
        url,
        method="get",
        data=None,
        params=None,
        headers={},
        **kwargs,
    ) -> Union[List[Dict], Dict]:
        """Implements SKYSQL API call"""

        self.url = self.autocomplete_url(url)
        self.headers = headers or self.auth_headers

        self.logger.debug(f"URL: {self.url} {self.headers}")

        if method.lower() == "get":
            r = requests.get(
                self.url,
                params=params,
                headers=self.headers,
                timeout=self.timeout,
                **kwargs,
            )
        elif method.lower() == "post":

            r = requests.post(
                self.url,
                data=json.dumps(data),
                headers=self.headers,
                timeout=self.timeout,
            )

        elif method.lower() == "patch":
            r = requests.patch(
                self.url,
                data=data,
                headers=self.headers,
                timeout=self.timeout,
            )
        elif method.lower() == "delete":
            r = requests.delete(
                self.url,
                params=params,
                headers=self.headers,
                timeout=self.timeout,
            )

        else:
            raise SkySQLAPIException(f"Method {method} is not supported")

        self.check_status_code(r)

        # An attempt to be smart and return JSON when it is applicable
        if self.is_json_response(r):
            return r.json()
        else:
            return {}

    def get_bearer_token(self) -> None:
        """get a bearer token for HTTP auth by using our API key"""
        if self.api_key is None:
            raise SkySQLAPIException("No SkySQL API key provided")
        url = f"{self.auth_url}/api/v1/token"
        headers = {
            "Authorization": f"Token {self.api_key}",
            "Content-length": "0",
        }
        r = self.post(url=url, headers=headers)
        self.logger.info(
            f"Tenant: {r.get('tenant_id')}, Project: {r.get('project_id')}, Full name: {r.get('full_name')}   "
        )
        self._bearer_token = r.get("token")

    def set_default_project_id(self):
        """Set project id to default one"""
        if self.project_id is None:
            projects = self.get(url=PROJECTS)
            for p in projects:
                if p.get("is_default"):
                    self.project_id = p.get("id")
                    self.logger.info(f"Set project id as {self.project_id}")
                    return
            raise SkySQLAPIException("There is no default project")

    def get_latest_version(self, topology: str) -> str:
        """Get the latest version for the topology. Use XBENCH_2_SKY_MAP to get one
        For now return one from the top
        """
        params = {"topology": topology, "limit": 100}
        versions = self.get(url=VERSIONS, params=params)
        if topology == "xpand-pg":  # TODO: hardcoded version, fix in next releases
            return "6.1.1"
        if len(versions) > 0:
            return versions[0].get("name")
        else:
            raise SkySQLAPIException(
                f"There are no version information for the topology {topology}"
            )

    def get_latest_release(self, product_name: str) -> str:
        """Get the latest release for the product. Apparently this is an admin interface which requires a special permissions
        Well, there is no sorting and no attributes which would tell which release is the latest.
        For now return one from the top

        Args:
            product_name (str): ['xpand','maxcscale','server']
        """
        releases = self.get(url=RELEASES, params={"limit": 100})
        for r in releases:
            if r.get("product_name") == product_name and r.get("is_active"):
                return r.get("version", "")
        return ""

    def get_services(self) -> List[Service]:
        """Get the list of all deployed databases"""
        services = []
        res = self.get(url=SERVICES)
        for r in res:
            services.append(from_dict(data_class=Service, data=r))
        return services

    def get_service_id_by_name(self, name: str) -> Optional[ServiceId]:
        """Get the service_id for the service
        Returns:
            str: service_id or None
        """
        services = self.get_services()
        for s in services:
            if s.name == name:
                return s.id
        return None

    def get_service_by_id(self, service_id: ServiceId) -> Service:
        """Get service details"""
        r = self.get_one(url=f"{SERVICES}/{service_id}")
        return from_dict(data_class=Service, data=r)

    def get_service_status(self, service_id) -> str:
        s = self.get_service_by_id(service_id)
        return s.status

    @retry(
        exceptions_to_check=SkySQLServicePending,
        exception_to_raise=SkySQLServiceFailed,
        max_delay=3600,
        delays=constant_delay(delay=60, attempts=60),
    )
    def wait_until_service_is_ready(self, service_id: ServiceId):
        self.logger.info(f"Waiting for the service be ready..")
        status = self.get_service_status(service_id)
        if status == ServiceState.ready:
            self.logger.info(f"Service is in {ServiceState.ready} state")
            return
        elif status == ServiceState.failed:
            raise SkySQLServiceFailed("Service failed!")
        else:
            raise SkySQLServicePending("Service is pending")

    def create_service(self, **kwargs) -> ServiceId:
        """Implements service/database provisioning. See service_param_names below for the list of fields expected"""

        service_name = kwargs.get("name", "")
        if len(service_name) > MAX_SERVICE_NAME_LENGTH:
            self.logger.warning(
                f"service name {service_name} is longer than {MAX_SERVICE_NAME_LENGTH} characters"
            )
            service_name = service_name[:MAX_SERVICE_NAME_LENGTH]
        self.logger.info(f"About to provision service {service_name}")
        existing_service_id = self.get_service_id_by_name(service_name)

        if existing_service_id is not None:
            self.logger.info(
                f"Found existing service with name {service_name}, will use that one"
            )
            return existing_service_id

        self.logger.info(f"Creating service {service_name}")
        service_param_names = [
            "name",
            "service_type",
            "version",
            "nodes",
            "size",
            "topology",
            "storage",
            "volume_iops",
            "volume_type",
            "ssl_enabled",
        ]
        service_params = {key: kwargs[key] for key in service_param_names}
        service_params["architecture"] = (
            service_params.get("architecture", None) or "amd64"
        )
        service_params["project_id"] = self.project_id
        service_params["region"] = self.region
        service_params["provider"] = self.provider
        res = self.post(url=SERVICES, data=service_params)
        return res.get("id", "")

    def delete_service(self, service_id: ServiceId):
        """Delete service. This function does for the actual deletion"""
        self.logger.info("Service has been submitted for deletion")
        self.delete(url=f"{SERVICES}/{service_id}")

    def allow_ip(
        self, service_id: ServiceId, ip_address: Optional[str] = local_ip_addr()
    ):
        """Add an ip address to the allow list.
        ip_address is just an ip address without mask
        """
        data = {"ip_address": f"{ip_address}/32"}
        self.post_only(url=f"{SERVICES}/{service_id}/security/allowlist", data=data)
        self.wait_until_service_is_ready(service_id)
        self.logger.info(f"IP address {ip_address} has been added to the whitelist")

    def get_credentials(self, service_id: ServiceId) -> Credentials:
        r = self.get_one(url=f"{SERVICES}/{service_id}/security/credentials")
        return from_dict(data_class=Credentials, data=r)

    def get_default_service_access_parameters(
        self, service_id: ServiceId
    ) -> Tuple[str, int, str, str]:
        """Get default access the service: host,port,password,username"""
        c = self.get_credentials(service_id)
        s = self.get_service_by_id(service_id)
        primary_endpoint = s.get_endpoint_by_name(name="primary")
        service_port = primary_endpoint.get_port_by_name("readwrite")
        return (s.fqdn, service_port.port, c.password, c.username)

    def start(self, service_id: ServiceId):
        """
        https://docs.skysql.mariadb.com/#/Services/post_provisioning_v1_services__service_id__power
        """
        self.post_only(url=f"{SERVICES}/{service_id}/power", data={"is_active": "true"})

    def stop(self, service_id: ServiceId):
        """
        https://docs.skysql.mariadb.com/#/Services/post_provisioning_v1_services__service_id__power
        """
        self.post_only(url=f"{SERVICES}/{service_id}/power", data={"is_active": "false"})
