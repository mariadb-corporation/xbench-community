import time
from typing import Optional

from cloud import VirtualMachine, VirtualNetwork
from cloud.abstract_cloud import AbstractCloud
from cloud.cloud_types import CloudTypeEnum
from cloud.exceptions import CloudException
from common import clean_cmd, get_class_from_klass, local_ip_addr
from compute import Node
from dacite import from_dict
from lib.mysql_client import ConnectionException, MySqlClient

from .exceptions import SkySQLAPIClientException, SkySQLCLoudException
from .skysql_api import SkySQLAPI
from .skysql_deployment import *


class SkySQLCloud(AbstractCloud[None, None]):

    def __init__(self, cluster_name: str, **kwargs):  # kwargs is cloud.yaml
        super(SkySQLCloud, self).__init__(cluster_name, **kwargs)
        self.sky_api = SkySQLAPI(**kwargs)
        self.client: Optional[MySqlClient] = None # Will be initiated in can_connect method
        self.db_instance = None # This is MariaDB or Xpand Class instance

    def cloud_type(self) -> CloudTypeEnum:
        return CloudTypeEnum.SkySql

    def can_connect(self, dbid: str, host: str, port: int) -> bool:
        # test if database is reachable with MySQL
        default_user, default_password = self.sky_api.get_credentials(dbid)
        default_database: str = "mysql"
        self.logger.debug(f"{host}, {default_user}, {port}, {default_password}")
        self.client = MySqlClient(
            host=host,
            port=port,
            user=default_user,
            password=default_password,
            database=default_database,
            connect_timeout=5,
            read_timeout=5,
        )
        try:
            self.client.connect()
        except ConnectionException:
            return False
        return True

    def wait_for_database_connectivity(self, instance: dict):
        retries = self.sky_api.max_api_call_polls
        self.logger.info("testing database connectivity")
        while retries:
            if self.can_connect(
                instance["id"], instance["ip_address"], int(instance["read_write_port"])
            ):
                self.logger.info("Connected to database")
                return
            else:
                retries -= 1
                time.sleep(self.sky_api.nap_time)
        raise Exception(
            f"could not connect to database after {self.sky_api.max_api_call_polls} after {self.sky_api.max_api_call_polls * self.sky_api.nap_time} seconds."
        )

    def is_running(self) -> bool:
        dbs = []

        try:
            dbs = self.sky_api.get_databases()
        except SkySQLAPIClientException as e:
            if e.status_code == 404:
                return False

        for db in dbs:
            if self.sky_api.convert_db_name(db["name"]) == self.sky_api.convert_db_name(
                self.cluster_name
            ):
                if db["install_status"] == SKYSQL_DB_IS_UP_AND_RUNNING:
                    return True
        return False

    def allow_driver_ips(self, drivers: list[dict], dbid: str):
        """need to get driver IP addresses which means the drivers
        must be created by this point

        how do I get the driver IP's???
        """
        for driver in drivers:
            self.sky_api.allow_ip(driver["ip_address"], dbid)

    def allow_local_ip(self, dbid: str):
        your_ip: str = local_ip_addr()
        self.sky_api.allow_ip(your_ip, dbid)

    def create_database_and_user(self):
        """
        create the benchmarking user with sufficient privileges and the benchmarking database
        """
        create_database_user_cmd = self.db_instance.create_database_and_user_stmt() # comes from launch_instances

        for stmt in clean_cmd(create_database_user_cmd).replace('\n','').split(';')[:-1]:
            self.logger.debug(f"running {stmt}")
            self.client.execute(stmt)

    def latest_version_for_deploy(self, deploy: str) -> str:
        """
        get version for a given deploy like
        "Distributed Transactions" / "xpand" -> "MariaDB Xpand 5.3.21"
        """
        self.logger.info(f"Getting latest release for {deploy}")
        deploy = deploy.lower()
        releases = self.sky_api.get_releases()
        self.logger.debug(releases)
        return releases[deploy]

    @staticmethod
    def check_kind(kind: str) -> str:
        try:
            deploy = SKYSQL_SERVICES_DEPLOYMENT_MAP[kind]
        except KeyError:
            raise SkySQLCLoudException(
                f"kind {kind} is invalid, use one of {list(SKYSQL_SERVICES_DEPLOYMENT_MAP.keys())}"
            )
        return deploy

    def check_for_databases(self, instance: dict) -> Optional[dict]:
        """
        if there is already a database ready for us to use that matches our cluster,
        then we want to use it, otherwise we will report
        """
        dbs = []
        self.logger.info("Getting list of databases to see if we are already deployed")
        # get the current list of databases
        try:
            dbs = self.sky_api.get_databases()
        except SkySQLAPIClientException as e:
            if e.status_code == 404:
                dbs = []

        if len(dbs) > 0:
            for db in dbs:
                # database is already there and ready for use
                if db["name"] == self.sky_api.convert_db_name(instance["cluster_name"]):
                    if db["install_status"] == SKYSQL_DB_IS_UP_AND_RUNNING:
                        self.logger.info(
                            f"database '{db['name']}' already deployed {db['id']} @ {db['ip_address']}"
                        )
                        return db
                    # database is being setup and we were impatient
                    elif db["install_status"] == SKYSQL_DB_IS_INSTALLING:
                        self.logger.error(
                            f"database '{db['name']}' is already being provisioned"
                        )
                        raise SkySQLCLoudException
                    # database is not usable
                    elif db["install_status"] in SKYSQL_DB_IS_BUSY:
                        self.logger.error(
                            f"database '{db['name']}' found but unusable.  Database is '{db['install_status']}'.  Try again after sometime or use a new name"
                        )
                        raise SkySQLCLoudException
        else:
            return None

    def launch_skysql_database(self, instance: dict):
        deploy = self.check_kind(instance["kind"])
        db_node = self.check_for_databases(instance)
        create_database_args = {
            "version": self.latest_version_for_deploy(SKYSQL_DEPLOY_2_RELEASE_MAP[instance["kind"]]),
            "region": self.sky_api.region,
            "cloud": self.sky_api.provider,
            "name": self.cluster_name,
            "replicas": instance["count"],
            "size": instance["instance_type"],
            "ssl": False, # TODO get proper SSL   instance["ssl"],
            "kind": deploy,
            "disk_size": instance["storage"]["size"],
            "iops": instance["storage"]["iops"],
        }
        # we don't already have a database to use
        if not db_node:
            self.logger.info(f"Launching database creation for {instance}")
            db_node = self.sky_api.create_db_cluster(**create_database_args)

        return db_node

    def launch_instances(self, instances: list[dict]) -> list[Optional["Node"]]:
        """ """
        instance: dict = instances[0]

        database_klass = get_class_from_klass(instance.get('klass', None))   # backend.SkySQLMariaDB or backend.SkySQLXpand

        # It is important to send kind to launch method - now it is coming from class property
        db_node = self.launch_skysql_database(instance | {'kind': database_klass.kind})

        # WARNING: this is tech debt
        # we are opening up our database to the world protected only by user and password
        # in the future we need to have explicit allowed IPs like this:
        # self.allow_local_ip(db_node["id"])
        # self.allow_driver_ips([], db_node["id"])
        # once we have a way of provisioning and getting the driver host ips
        # some options include:
        # - post_install hook added to AbstractBackend and called before workload run
        # - create a security group in the cloud to store a list of IPs, then read that SG and allow those IPs
        self.sky_api.allow_ip("0.0.0.0/0", db_node["id"])
        self.wait_for_database_connectivity(db_node)

        # Let's create a proper Node to return
        vm = from_dict(data_class=VirtualMachine, data=instance)
        vm.cloud = db_node["provider"]
        vm.id = db_node["id"]
        vm.instance_type = db_node["size"]
        vm.network = VirtualNetwork(
            cloud_type="public_cloud", public_ip=db_node["ip_address"]
        )
        vm.zone = "not a real zone"
        vm.cluster_name = self.cluster_name
        node: Node = Node(vm)

        self.db_instance = database_klass(node)
        # I need to create xpand user first
        self.create_database_and_user()
        self.db_instance.db_connect()

        return [node]

    def launch_instance(self, **instance_params) -> Optional[Node]:
        raise CloudException(f"Not implemented. Does not apply to {__name__}")

    def terminate_instance(self, instance: Node, terminate_storage: bool = False):
        raise CloudException(f"Not implemented. Does not apply to {__name__}")

    def terminate_instances(self, instances: list[Node], terminate_storage: bool = True):
        dbid: str = instances[0].vm.id
        self.sky_api.destroy(dbid)

    def stop_instances(self, instances: list[Node]):
        self.logger.warning("SkySQL version 1 does not support starting and stopping your database through the API.  "
                            "Use the web console instead")

    def start_instances(self, instances: list[Node]):
        self.logger.warning("SkySQL version 1 does not support starting and stopping your database through the API.  "
                            "Use the web console instead")