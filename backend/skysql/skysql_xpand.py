from backend.base_backend import SingleUnManagedBackend
from backend.xpand.base_xpand_backend import BaseXpandBackend
from backend.xpand.xpand_config import XpandConfig
from compute import BackendTarget
from compute.backend_product import BackendProduct

from ..abstract_backend import AbstractBackend

XPAND_CONFIG_FILE = "xpand.yaml"


class SkySQLXpand(SingleUnManagedBackend, BaseXpandBackend, AbstractBackend):
    """
    SkySQL can deploy Mariadb, Columnstore, and Xpand
    so the methods and fields in this class should be generic to all
    """

    clustered = False
    product = BackendProduct.xpand
    kind = "xpand"  # This is SkySQL default type for Xpand, see SkySQLDeployment

    def __init__(self, node, **kwargs):

        SingleUnManagedBackend.__init__(
            self,
            node=node,
            backend_config_yaml_file=XPAND_CONFIG_FILE,
            backend_config_klass=XpandConfig,
        )

        bt_target = self.config.db
        bt_target.host = node.vm.network.get_public_iface()
        BaseXpandBackend.__init__(self, bt_target)

    def configure(self):
        pass

    def install(self) -> "BackendTarget":
        return self.config.db

    def clean(self):
        pass

    def start(self, **kwargs):
        pass

    def stop(self, **kwargs):
        pass

    def post_data_load(self, database: str):
        pass

    def pre_workload_run(self):
        pass

    def pre_thread_run(self):
        pass

    def create_database_and_user_stmt(self) -> str:
        mysql_cmd = f"""
        create database if not exists {self.config.db.database};
        create user if not exists '{self.config.db.user}'@'%' identified by '{self.config.db.password}';
        GRANT ALTER, ALTER ROUTINE, CREATE, CREATE ROUTINE, CREATE TEMPORARY TABLES, CREATE USER, CREATE VIEW, DELETE, DROP, EXECUTE, INDEX, INSERT, LOCK TABLES, PROCESS, RELOAD, SELECT, SHOW DATABASES, SHOW VIEW, TRIGGER, UPDATE ON *.* TO '{self.config.db.user}'@'%';
        flush privileges;
        """
        return mysql_cmd

    def get_logs(self):
        pass
