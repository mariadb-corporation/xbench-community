from typing import List

from backend import DummyBackend
from backend.base_backend import MultiManagedBackend, MultiUnManagedBackend
from backend.base_mysql_backend import BaseMySqlBackend
from compute import BackendTarget
from compute.backend_dialect import BackendDialect
from compute.backend_product import BackendProduct
from compute.node import Node

from .tidb_config import TiDBConfig

TIDB_CONFIG_FILE = "tidb.yaml"

ssh_cmd = """
    sed -i "s/\#MaxSessions 10/MaxSessions 20/g" /etc/ssh/sshd_config
    systemctl restart sshd
"""
class TiKV(DummyBackend, MultiManagedBackend):
    """Fake class for TiDB"""

    clustered = True
    dialect = BackendDialect.mysql
    product = BackendProduct.tidb

    def __init__(
        self,
        nodes: List[Node],
        **kwargs,
    ):
        MultiManagedBackend.__init__(
            self,
            nodes=nodes,
            backend_config_yaml_file=TIDB_CONFIG_FILE,
            backend_config_klass=TiDBConfig,
        )

    def configure(self):
        # this is being called like a classmethod, but it is not, so we
        # have to explicitly pass self
        try:
            self.logger.info('Updating ssh config')
            self.run_on_all_nodes(ssh_cmd, sudo=True)
        except Exception as e:
            pass
        finally:
            return MultiManagedBackend.configure(self)

class TiDB(DummyBackend, BaseMySqlBackend, MultiUnManagedBackend):
    """Fake class for TiDB"""

    clustered = True
    dialect = BackendDialect.mysql
    product = BackendProduct.tidb

    def __init__(
        self,
        nodes: List[Node],
        **kwargs,
    ):
        MultiUnManagedBackend.__init__(
            self,
            nodes=nodes,
            backend_config_yaml_file=TIDB_CONFIG_FILE,
            backend_config_klass=TiDBConfig,
        )
        BaseMySqlBackend.__init__(self, bt=self.config.db)

    def configure(self):
        # this is being called like a classmethod, but it is not, so we
        # have to explicitly pass self
        try:
            self.logger.info('Updating ssh config')
            self.run_on_all_nodes(ssh_cmd, sudo=True)
        except Exception as e:
            pass

    def install(self) -> BackendTarget:
        return self.config.db


class TiPD(DummyBackend, MultiManagedBackend):
    """Fake class for TiDB"""

    clustered = True
    dialect = BackendDialect.mysql
    product = BackendProduct.tidb

    def __init__(
        self,
        nodes: List[Node],
        **kwargs,
    ):
        MultiManagedBackend.__init__(
            self,
            nodes=nodes,
            backend_config_yaml_file=TIDB_CONFIG_FILE,
            backend_config_klass=TiDBConfig,
        )

    def configure(self):
        # this is being called like a classmethod, but it is not, so we
        # have to explicitly pass self
        try:
            self.logger.info('Updating ssh config')
            self.run_on_all_nodes(ssh_cmd, sudo=True)
        except Exception as e:
            pass
        finally:
            return MultiManagedBackend.configure(self)
