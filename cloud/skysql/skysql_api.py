import json
import logging
import time
from enum import Enum

import requests

from .exceptions import (
    SkySQLAPIClientException,
    SkySQLAPIException,
    SkySQLAPIServerException,
)

from .skysql_deployment import *


class SkySQLAccountTier(str, Enum):
    power = "Power"
    foundation = "Foundation"

    def __repr__(self):
        return self.value


class SkySQLServiceState(str, Enum):
    running = "Running"
    pending = "Pending"
    paused = "Paused"
    starting = "Starting"
    stopped = "Stopped"
    stopping = "Stopping"
    terminated = "Terminated"
    terminating = "Terminating"

    def __repr__(self):
        return self.value


class SkySQLAPI:
    """Install Xpand on SkySQL with terraform
    1. No VM's.  SkySQL is cloud hosted, so we don't have machines
    2. No Operating Systems to manage
    3. No storage volumes.  SkySQL handles provisioning cloud storage and volume setup
    4. No SSH
    5. Need to handle SSL
    """

    clustered: bool = True
    skysql_account_tier: SkySQLAccountTier = SkySQLAccountTier.power
    nap_time: int = 60  # seconds to wait on polling the API
    max_api_call_polls: int = 60  # wait up to an hour

    def __init__(self, **kwargs):
        self.api_key = ""
        self.region = ""
        self.provider = ""
        self.api_server = ""
        self.id_server = ""
        self.nap_time = SkySQLAPI.nap_time
        self.max_api_call_polls = SkySQLAPI.max_api_call_polls

        allowed_keys = list(self.__dict__.keys())
        self.__dict__.update(
            (key, value) for key, value in kwargs.items() if key in allowed_keys
        )

        self._bearer_token = None
        self.logger = logging.getLogger(__name__)
        self.get_bearer_token()

    def _api_call(
        self, url: str, method: str, headers=None, data=None, params=None
    ) -> requests.Response:

        self.logger.debug(f"\n {url} \n {method} \n {headers} \n {data} {params} ")
        if headers is None:
            headers = {}
        if params is None:
            params = {}

        method = method.lower()
        req_headers: dict[str, str] = {}

        if self._bearer_token is not None:
            req_headers["Authorization"] = f"Bearer {self._bearer_token}"
        req_headers.update(headers)

        res = None
        if method == "get":
            res = requests.get(url, headers=req_headers, params=params)
        elif method == "post":
            res = requests.post(url, headers=req_headers, data=data, params=params)
        elif method == "delete":
            res = requests.delete(url, headers=req_headers, params=params)

        # TODO: deal with expired JWT
        """
        if res.status_code == 401:
            try:
                if "JWT is expired" in res.json()["detail"]:
                    self.get_bearer_token()
            except KeyError:
                res.raise_for_status()
            # retry
            self._api_call(url, method, headers=headers, data=data, params=params)
        """

        self.logger.debug(f"{method.upper()} {url} {res.status_code} {res.reason}")
        if not res.ok:
            err_msg: str = f"{res.reason} {res.text}"
            if 400 <= res.status_code < 500:
                raise SkySQLAPIClientException(
                    status_code=res.status_code, message=err_msg, response=res
                )
            elif res.status_code >= 500:
                raise SkySQLAPIServerException(
                    status_code=res.status_code, message=err_msg, response=res
                )

        return res

    def get_bearer_token(self):
        """get a bearer token for HTTP auth by using our API key
        https://mariadb.com/products/skysql/docs/security/api-key/#api-key-bearer-token

        with a temporarily valid token we can make API calls to allow
        our IP address for subsequent calls

        curl --location --request POST \
       --header 'Authorization: Token SKYSQL_API_KEY' \
       --header 'Content-length: 0' \
       https://id.mariadb.com/api/v1/token/
        """
        if self.api_key is None:
            raise SkySQLAPIException("No SkySQL API key provided")
        api_token_path: str = "/api/v1/token"
        url: str = f"{self.id_server}{api_token_path}"
        headers = {
            "Authorization": f"Token {self.api_key}",
            "Content-length": "0",
        }
        res: requests.Response = self._api_call(url, "post", headers=headers)
        d: dict = res.json()
        self._bearer_token = d["token"]

    def get_databases(self):
        """get the list of all deployed databases
        https://mariadb.com/products/skysql/docs/reference/skyapi/api/List_Services/
        """
        databases_path: str = "/services/"
        url: str = f"{self.api_server}{databases_path}"
        res: requests.Response = self._api_call(url, "get")
        return res.json()

    def get_database(self, db: str) -> dict:
        databases_path: str = f"/services/{db}"
        url: str = f"{self.api_server}{databases_path}"
        res: requests.Response = self._api_call(url, "get")
        return res.json()

    def get_credentials(self, dbid: str) -> tuple:
        """get the current credentials for the newly created xpand cluster
        https://mariadb.com/products/skysql/docs/interfaces/dbaas-api/rest/#obtain-database-credentials

        once we have to credentials we can setup our MySQL client
        curl --location \
        --header 'Authorization: Bearer SKYSQL_BEARER_TOKEN' \
        https://api.skysql.net/services/db00000001/security/credentials/
        """
        credentials_path: str = f"/services/{dbid}/security/credentials"
        url: str = f"{self.api_server}{credentials_path}"
        res: requests.Response = self._api_call(url, "get")
        d: dict = res.json()
        return d["username"], d["password"]

    def _allow_ip(self, ip: str, dbid: str) -> dict:
        """need to have local ip allowed to connect to the new cluster

        here is a curl using GET to check the allow list
        curl -v -L -H "Authorization: Bearer ${skysql_token}" \
        https://api.skysql.net/services/db00006905/security/allowlist

        or maybe this works
        https://mariadb.com/products/skysql/docs/interfaces/dbaas-api/rest/#add-ip-address-to-allowlist
        https://mariadb.com/products/skysql/docs/reference/skyapi/api/Read_Allowlist_Status/
        """
        req_data: dict[str, str] = {"ip_address": ip}
        allowlist_path: str = f"/services/{dbid}/security/allowlist"
        url = f"{self.api_server}{allowlist_path}"
        res = requests.Response = self._api_call(url, "post", data=json.dumps(req_data))
        return res.json()

    def allow_ip(self, ip: str, dbid: str):
        self.logger.debug(f"allowing ip {ip} for database {dbid}")
        self._allow_ip(ip, dbid)
        allowed_ips = self.get_allow_list(dbid)
        retries = SkySQLAPI.max_api_call_polls

        for allowed_ip in allowed_ips:
            if allowed_ip["ip_address"] == ip:
                self.logger.info(f"allowed ips {allowed_ips}")
                return

        while retries:
            for allowed_ip in allowed_ips:
                if allowed_ip["ip_address"] == ip:
                    self.logger.info(f"allowed ips {allowed_ips}")
                    return
            retries -= 1
            time.sleep(SkySQLAPI.nap_time)

        self.logger.error(
            f"failed to allow ip {ip} after {SkySQLAPI.max_api_call_polls} tries and over {SkySQLAPI.max_api_call_polls * SkySQLAPI.nap_time} seconds."
        )
        raise SkySQLAPIServerException(f"could not allow ip address {ip}")

    def get_providers(self) -> list:
        providers_path: str = "/offering/providers"
        url = f"{self.api_server}{providers_path}"
        res: requests.Response = self._api_call(url, "get")
        return res.json()

    def check_provider(self, cloud: str) -> bool:
        providers: list = self.get_providers()
        for p in providers:
            if p["active"] == "true":
                if p["name"] == cloud or p["value"] == cloud:
                    return True
        return False

    def get_regions(self, provider: str) -> list:
        regions_path: str = "/offering/regions"
        url = f"{self.api_server}{regions_path}"
        res: requests.Response = self._api_call(
            url, "get", params={"provider": provider}
        )
        return res.json()

    def check_region(self, region: str, provider: str) -> bool:
        regions = self.get_regions(provider)
        for r in regions:
            if r["name"] == region:
                return True
        return False

    def get_deployments(self) -> list:
        service_types_path = "/offering/service-types"
        url: str = f"{self.api_server}{service_types_path}"
        res: requests.Response = self._api_call(url, "get")
        return res.json()

    def check_deployment(self, deploy: str) -> bool:
        service_types = self.get_deployments()
        for s in service_types:
            for topo in s["active_topologies"].split(", "):
                if deploy == topo:
                    return True
        return False

    def check_aws_iops(self, disk_size, iops) -> int:
        aws_small_volume_size: int = 2000  # 2000G or 2T
        aws_small_volume_iops_per_gig_limit: int = 50
        aws_large_volume_iops_per_gig_limit: int = 60_000
        if (
            disk_size < aws_small_volume_size
            and iops > aws_small_volume_iops_per_gig_limit * disk_size
        ):
            # error or provide max iops for volume size
            max_iops = disk_size * aws_small_volume_iops_per_gig_limit
            self.logger.warning(
                f"total iops {iops} for volume size {disk_size} is above the limit of 50 iops / GB.  Setting iops to maximum of {max_iops}"
            )
            return max_iops

        elif (
            disk_size > aws_small_volume_size
            and iops > aws_large_volume_iops_per_gig_limit * disk_size
        ):
            # error or provide max iops for volume size
            max_iops = disk_size * aws_large_volume_iops_per_gig_limit
            self.logger.warning(
                f"total iops {iops} for volume size {disk_size} is above the limit of 50 iops / GB.  Setting iops to maximum of {max_iops}"
            )
            return max_iops
        else:
            return iops

    def get_releases(self) -> dict[str, str]:
        """get release versions and match to version of Xpand

        SkySQL doesn't support all versions of Xpand, so we will try our best
        to map the requested version to a SkySQL release

        curl -L -H "Authorization: Bearer ${skysql_token}" \
        'https://api.skysql.net/offering/versions' \
        | jq '.[] | select(.service_type == "Xpand")'
        """
        versions_path: str = "/offering/versions"
        url: str = f"{self.api_server}{versions_path}"
        # Default limit is 10, we may need to revisit url param if versions exceed 100
        res: requests.Response = self._api_call(url, "get", params={"limit": 100})
        releases: dict = res.json()
        return {
            release["service_type"].lower(): release["name"] for release in releases
        }

    def get_sizes(self, params: dict) -> list:
        """
        curl -L -H "Authorization: Bearer ${sky_token}" \
        'https://api.skysql.net/offering/sizes? \
        tier=Power&region=us-west-2&provider=aws&topology=Distributed%20Transactions'
        """
        sizes_path: str = "/offering/sizes"
        url: str = f"{self.api_server}{sizes_path}"
        res: requests.Response = self._api_call(url, "get", params=params)
        return res.json()

    def check_size(self, size: str, cloud: str, kind: str, region: str) -> bool:
        params = {
            "tier": SkySQLAPI.skysql_account_tier,
            "provider": cloud,
            "topology": kind,
            "region": region,
        }
        sizes = self.get_sizes(params)
        for s in sizes:
            if s["name"] == size:
                return True
        return False

    def check_db_name(self, db_name: str) -> str:
        max_database_name_length: int = 24
        if len(db_name) > max_database_name_length:
            self.logger.warning(
                f"database name {db_name} is longer than 25 characters, so we are using {db_name[:max_database_name_length]}"
            )
            return db_name[:max_database_name_length]
        return db_name

    def get_allow_list(self, dbid: str) -> list:
        """need this for polling to know when our IP address is allowed"""
        allowlist_path: str = f"/services/{dbid}/security/allowlist"
        url: str = f"{self.api_server}{allowlist_path}"
        res: requests.Response = self._api_call(url, "get")
        return res.json()

    def db_status_is_up(self, dbid: str) -> bool:
        """might need this to poll so we know when our database is ready

        https://mariadb.com/products/skysql/docs/interfaces/dbaas-api/rest/#check-service-status
        curl --location \
        --header 'Authorization: Bearer SKYSQL_BEARER_TOKEN' \
        https://api.skysql.net/services/db00000001/status/
        """
        service_status_path: str = f"/services/{dbid}/status"
        url: str = f"{self.api_server}{service_status_path}"
        res: requests.Response = self._api_call(url, "get")
        status_res: dict = res.json()
        status: str = status_res["status"]

        if status != SkySQLServiceState.running:
            self.logger.debug(
                f"waiting on database creation...  current state is {status}"
            )
            return False
        else:
            self.logger.debug(f"database {dbid} ready!")
            return True

    def db_has_ip(self, dbid: str):
        # TODO: add regex check for ip address
        service_path: str = f"/services/{dbid}"
        url: str = f"{self.api_server}{service_path}"
        res: requests.Response = self._api_call(url, "get")
        service_res: dict = res.json()
        ip: str = service_res["ip_address"]
        port: str = service_res["read_write_port"]
        fqdn: str = service_res["fqdn"]

        if ip == "" or port == "" or fqdn == "":
            self.logger.debug(f"waiting for database to acquire ip address...")
            return False
        else:
            self.logger.debug(f"database acquired ip {ip}")
            return True

    @staticmethod
    def convert_db_name(name: str) -> str:
        # Valid names may only contain lowercase letters, digits and hyphens up to 24 characters in length
        prefix: str = "mdbint"
        replace_chars: str = name.replace("_", "-")
        apply_prefix_and_done: str = f"{prefix}-{replace_chars}"
        return apply_prefix_and_done

    def check_db_cluster_create_params(
        self,
        cloud: str,
        region: str,
        kind: str,
        size: str,
        replicas: int,
    ):
        if not self.check_provider(cloud):
            raise SkySQLAPIException(f"cloud provider {cloud} is invalid")
        if not self.check_region(region, cloud):
            raise SkySQLAPIException(f"region {region} is not valid for cloud {cloud}")
        if not self.check_deployment(kind):
            raise SkySQLAPIException(f"deployment {kind} is not valid")
        if not self.check_size(size, cloud, kind, region):
            raise SkySQLAPIException(f"compute size {size} is invalid")
        if replicas < 3 and kind == SkySQLDeployment.xpand:
            raise SkySQLAPIException(
                f"must use a minimum of 3 replicas for '{SkySQLDeployment.xpand}', you tried using {replicas} replicas"
            )

    def _create_db_cluster(
        self,
        version: str,
        region: str,
        cloud: str,
        name: str,
        replicas: int,
        size: str,
        kind: str,
        disk_size: int,
        iops: int,
        ssl: bool = False,
    ) -> dict:
        """create database with config data

        https://mariadb.com/products/skysql/docs/reference/skyapi/api/Create_Service/
        curl --location --request POST \
       --header 'Authorization: Bearer SKYSQL_BEARER_TOKEN' \
       --header 'Content-type: application/json' \
       --data '@request.json' \
       https://api.skysql.net/services/

        curl -XPOST -L -H "Authorization: Bearer ${sky_token}" \
        -H "Content-type: application/json" \
        -d '{"release_version": "MariaDB Xpand 5.3.21", \
        "region": "us-west-2", "provider": "aws", "replicas": "3", \
        "size": "Sky-4x16", "ssl": false, "topology": "Distributed Transactions", \
        "tx_storage": "100", "iops": "100", \
        "name": "my-xpand-from-api", "tier": "Power"}' \
        https://api.skysql.net/services

        {
          "name": "my-xpand-from-api",
          "tx_storage": "",
          "maxscale_config": "",
          "maxscale_proxy": "false",
          "monitor": "false",
          "provider": "Amazon AWS",
          "region": "us-west-2",
          "release_version": "MariaDB Xpand 5.3.21",
          "replicas": "3",
          "size": "Sky-4x16",
          "tier": "Power",
          "topology": "Distributed Transactions",
          "volume_iops": "100",
          "ssl_tls": "Enabled",
          "owned_by": "xbench",
          "id": "db00006961",
          "custom_config": "",
          "fqdn": "",
          "install_status": "Pending Install",
          "ip_address": "",
          "number": "DB00006961",
          "read_only_port": "",
          "read_write_port": "",
          "created_on": "2022-06-27 09:23:07",
          "updated_on": "2022-06-27 09:23:07"
        }

        """
        cloud = cloud.lower()
        size = size.capitalize()
        services_path: str = "/services/"
        url: str = f"{self.api_server}{services_path}"
        use_ssl: str = "Enabled" if ssl else "Disabled"
        # we want to avoid alerting on these databases
        db_name: str = self.check_db_name(self.convert_db_name(name))
        if cloud == "aws":
            iops = self.check_aws_iops(disk_size, iops)
        # it would be cool in the future if the config specified a 'kind' of 'mariadb'
        # and based on the 'count' field we set it to 'SkySQLDeployment.standalone_mariadb' if count is 1
        # and 'SkySQLDeployment.replicated_mariadb' with replicas if the 'count' > 1
        if kind == SkySQLDeployment.standalone_mariadb:
            replicas = 0

        self.check_db_cluster_create_params(cloud, region, kind, size, replicas)

        req_data: str = json.dumps(
            {
                "name": db_name,
                "provider": cloud,
                "region": region,
                "release_version": version,
                "replicas": str(replicas),
                "size": size,
                "ssl_tls": use_ssl,
                "tier": SkySQLAPI.skysql_account_tier,
                "topology": kind,
                "tx_storage": str(disk_size),
                "volume_iops": str(iops),
            }
        )
        headers: dict = {
            "Content-type": "application/json",
        }
        self.logger.info(
            f"""
            creating database {name}
            cloud/region: {cloud} / {region}
            engine/version: {kind} / {version}
            disk_size/iops: {disk_size} / {iops}
            """
        )
        res: requests.Response = self._api_call(
            url, "post", headers=headers, data=req_data
        )
        d: dict = res.json()
        self.logger.info(f"database creation started")
        return d

    def create_db_cluster(self, **kwargs) -> dict:
        db: dict = self._create_db_cluster(**kwargs)
        retries: int = SkySQLAPI.max_api_call_polls

        while retries:
            if self.db_status_is_up(db["id"]):
                self.logger.info("database process is ready")
                break
            else:
                retries -= 1
                time.sleep(SkySQLAPI.nap_time)

        while retries:
            if self.db_has_ip(db["id"]):
                db = self.get_database(db["id"])
                self.logger.info(
                    f"database is now listening at {db['fqdn']} on port {db['read_write_port']}"
                )
                return db
            else:
                retries -= 1
                time.sleep(SkySQLAPI.nap_time)

        self.logger.error(
            f"failed to create database after {SkySQLAPI.max_api_call_polls} after {SkySQLAPI.max_api_call_polls * SkySQLAPI.nap_time} seconds."
        )
        raise SkySQLAPIServerException("could not create database")

    def destroy(self, dbid: str):
        """delete a provisioned database

        https://mariadb.com/products/skysql/docs/interfaces/dbaas-api/rest/#delete-a-database-service
        curl --location --request DELETE \
        --header 'Authorization: Bearer SKYSQL_BEARER_TOKEN' \
        https://api.skysql.net/services/db00000001/
        """
        self.logger.info(f"destroying database {dbid}")
        service_path: str = f"/services/{dbid}"
        url: str = f"{self.api_server}{service_path}"
        self._api_call(url, "delete")
