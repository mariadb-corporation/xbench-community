from dataclasses import dataclass
from enum import Enum
from typing import List, NewType

from cloud.skysql.exceptions2 import SkySQLAPIException


@dataclass
class Credentials:
    host: str
    username: str
    password: str


@dataclass
class ServicePort:
    name: str
    port: int
    purpose: str


@dataclass
class ServiceEndpoint:
    name: str
    ports: List[ServicePort]

    def get_port_by_name(self, port_name: str = "readwrite") -> ServicePort:

        for p in self.ports:
            if p.name == port_name:
                return p
        raise SkySQLAPIException(f"There is no port  {port_name}")


ServiceId = NewType("ServiceId", str)


@dataclass
class Service:
    """Service/Cluster/Database in the SkySQL
    https://api.mariadb.com/public/services/dps/docs/swagger/index.html#/private_api%3Atrue/get_provisioning_v1_internal_services__service_id_
    """

    id: ServiceId
    name: str
    status: str
    tier: str
    topology: str
    provider: str
    region: str
    endpoints: List[ServiceEndpoint]
    fqdn: str = ""

    def get_endpoint_by_name(self, name: str = "primary") -> ServiceEndpoint:
        for e in self.endpoints:
            if e.name == name:
                return e
        raise SkySQLAPIException(f"There is no endpoint {name}")


class ServiceState(str, Enum):
    ready = "ready"
    pending = "pending_create"
    failed = "failed"

    def __repr__(self):
        return self.value
