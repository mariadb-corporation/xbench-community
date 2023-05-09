from copy import deepcopy
from typing import List, Optional, Tuple

from dacite import from_dict

from cloud import VirtualMachine, VirtualNetwork
from cloud.abstract_cloud import AbstractCloud
from cloud.cloud_types import CloudTypeEnum
from cloud.exceptions import CloudException
from cloud.skysql.skysql2_deployment import XBENCH_2_SKY_ARCH_MAP, XBENCH_2_SKY_MAP
from common import clean_cmd, get_class_from_klass
from compute import Node
from lib.mysql_client import MySqlClient
from lib.xbench_config import XbenchConfig
from xbench.common import get_default_cluster

from .skysql_api2 import SkySQLAPI2


class SkySQLCloud2(AbstractCloud[None, None]):
    def __init__(self, cluster_name: str, **kwargs):  # kwargs is cloud.yaml
        super(SkySQLCloud2, self).__init__(cluster_name, **kwargs)
        self.sky_api = SkySQLAPI2(**kwargs)

        self.cluster_name = XbenchConfig().cluster_name()
        self.backend_klass_instance = (
            None  # backend.SkySQLMariaDB or backend.SkySQLXpand
        )

    def cloud_type(self) -> CloudTypeEnum:
        return CloudTypeEnum.SkySql2

    def all_drivers_public_ips(self) -> List[str]:
        all_ips: List[str] = []
        cluster = get_default_cluster()
        driver_nodes = cluster.get_all_driver_nodes()
        for n in driver_nodes:
            all_ips.append(n.vm.network.get_public_iface())
        return all_ips

    def create_database_and_user(
        self,
    ):
        """
        create the benchmarking user with sufficient privileges and the benchmarking database
        """
        sql_cmd = self.backend_klass_instance.create_database_and_user_stmt()
        if sql_cmd:
            create_database_user_cmd = (sql_cmd)

            for stmt in (
                clean_cmd(create_database_user_cmd).replace("\n", "").split(";")[:-1]
            ):
                self.logger.debug(f"running {stmt}")
                self.client.execute(stmt)

    @staticmethod
    def mysql_client(host, port, password, user):

        return MySqlClient(
            host=host,
            port=port,
            user=user,
            password=password,
            database="mysql",
            connect_timeout=5,
            read_timeout=5,
        )

    def launch_skysql_service(self, instance: dict) -> Tuple:
        """Create service, white list drivers, check connectivity

        Args:
            instance (dict): _description_

        Returns:
            Service: _description_
        """

        product = self.backend_klass.product  # We just added this in launch_instances
        service_params = {
            "architecture": XBENCH_2_SKY_ARCH_MAP[instance.get("arch", "")],
            "name": self.cluster_name,
            "service_type": XBENCH_2_SKY_MAP[product].get("service_type"),
            "provider": self.sky_api.provider,
            "region": self.sky_api.region,
            "version": self.sky_api.get_latest_version(
                XBENCH_2_SKY_MAP[product].get("topology", "")
            ),
            "nodes": instance["count"],
            "size": instance["instance_type"].lower(),
            "topology": XBENCH_2_SKY_MAP[product].get("topology"),
            "storage": instance["storage"]["size"],
            "volume_type": instance["storage"].get("type", "io1"),
            "volume_iops": instance["storage"]["iops"],
            "ssl_enabled": False,
        }

        # Create service, wait until whitelisting
        self.logger.debug(f"Creating service with {service_params}")
        service_id = self.sky_api.create_service(**service_params)
        self.sky_api.wait_until_service_is_ready(service_id)
        # whitelisting
        self.sky_api.allow_ip(service_id)  # It will add local IP
        # All drivers ips
        for ips in self.all_drivers_public_ips():
            self.sky_api.allow_ip(service_id, ips)

        (
            host,
            port,
            password,
            username,
        ) = self.sky_api.get_default_service_access_parameters(service_id)

        # Let's create MySQL client
        self.logger.info(
            f"Connecting to service using {host}, {port}, {username}, {password} "
        )
        self.client = self.mysql_client(host, port, password, username)
        self.client.connect()

        return (service_id, host)

    def launch_instances(self, instances: list[dict]) -> list[Optional["Node"]]:
        """ """
        node_count = len(instances)
        instance: dict = instances[0]

        # backend.SkySQLMariaDB or backend.SkySQLXpand
        self.backend_klass = get_class_from_klass(instance.get("klass", None))

        # It is important to send kind to launch method - now it is coming from class property
        service_id, host = self.launch_skysql_service(instance)

        # Let's create a proper Node to return
        vm = from_dict(data_class=VirtualMachine, data=instance)
        vm.cloud = self.sky_api.provider
        vm.id = service_id
        vm.instance_type = instance["instance_type"]
        vm.network = VirtualNetwork(cloud_type="public_cloud", public_ip=host)
        vm.zone = "not a real zone"
        vm.cluster_name = self.cluster_name
        node: Node = Node(vm)
        #
        self.backend_klass_instance = self.backend_klass(node)
        # I need to create xbench user first
        self.create_database_and_user()
        self.logger.info("Connecting to database using xbench credentials")
        self.backend_klass_instance.db_connect()

        # We always return only one instance - primary.
        # In case of read-only I just have to return list.
        returned_nodes: List[Node] = []
        if node_count > 1:
            for i in instances:
                read_only_vm = deepcopy(vm)
                read_only_vm.name = i.get(
                    "name", ""
                )  # I have to change name as this is a key in cluster file
                returned_nodes.append(Node(read_only_vm))
        else:
            returned_nodes = [Node(vm)]
        return returned_nodes

    def launch_instance(self, **instance_params) -> Optional[Node]:
        raise CloudException(f"Not implemented. Does not apply to {__name__}")

    def terminate_instance(self, instance: Node, terminate_storage: bool = False):
        raise CloudException(f"Not implemented. Does not apply to {__name__}")

    def terminate_instances(
        self, instances: list[Node], terminate_storage: bool = True
    ):
        self.sky_api.delete_service(instances[0].vm.id)

    def stop_instances(self, instances: list[Node]):
        self.sky_api.stop(instances[0].vm.id)

    def start_instances(self, instances: list[Node]):
        self.sky_api.start(instances[0].vm.id)
