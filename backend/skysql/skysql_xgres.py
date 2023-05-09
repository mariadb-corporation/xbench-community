from backend.base_backend import SingleUnManagedBackend
from backend.xpand.base_xpand_backend import BaseXpandBackend
from backend.xpand.xpand_config import XpandConfig
from compute import BackendTarget
from compute.backend_product import BackendProduct

from ..abstract_backend import AbstractBackend

XPAND_CONFIG_FILE = "xpand.yaml"


class SkySQLXgres(SingleUnManagedBackend, BaseXpandBackend, AbstractBackend):
    """
    SkySQL can deploy Mariadb, Columnstore, Xpand and Xgres
    so the methods and fields in this class should be generic to all
    """

    clustered = False
    product = BackendProduct.xgres
    kind = "xgres"  # This is SkySQL default type for Xgres, see SkySQLDeployment

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
        return ""

    def get_logs(self):
        pass
