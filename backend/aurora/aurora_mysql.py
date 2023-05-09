# -*- coding: utf-8 -*-
# Copyright (C) 2022 dvolkov


from compute import Node
from compute.backend_product import BackendProduct
from compute.backend_target import BackendTarget
from lib.mysql_client import MySqlClientException

from ..abstract_backend import AbstractBackend
from ..base_backend import SingleUnManagedBackend
from ..base_mysql_backend import BaseMySqlBackend
from .aurora_mysql_config import AuroraMySqlConfig
from .exceptions import AuroraMySqlException

AURORA_CONFIG_FILE = "aurora_mysql.yaml"


class AuroraMySql(SingleUnManagedBackend, BaseMySqlBackend, AbstractBackend):
    """Generic class for AuroraMySql"""

    clustered = False
    product = BackendProduct.aurora_mysql


    def __init__(
        self,
        node: Node,
        **kwargs,
    ):
        SingleUnManagedBackend.__init__(
            self,
            node=node,
            backend_config_yaml_file=AURORA_CONFIG_FILE,
            backend_config_klass=AuroraMySqlConfig,
        )
        BaseMySqlBackend.__init__(self, bt=self.config.db)

    def configure(self):
        # Aurora doesn't create database by default.
        database = self.connect_params["database"]
        self.connect_params["database"] = None
        query = f"create database if not exists {self.config.db.database}"
        self.db_connect()
        self.execute(query)
        self.connect_params["database"] = database

    def install(self) -> BackendTarget:
        self.db_connect()
        self.print_db_version()
        # BT target is for drivers, so we need to re-adjust how drivers are going to connect
        self.config.db.host = self.node.vm.network.get_client_iface()
        return self.config.db

    def print_non_default_variables(self):
        try:
            # Aurora doesn't have SYSTEM_VARIABLES, look at parameter groups
            pass

        except MySqlClientException as e:
            raise AuroraMySqlException(e)

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

    def get_logs(self):
        pass
