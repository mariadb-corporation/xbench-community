# -*- coding: utf-8 -*-
# Copyright (C) 2022 dvolkov

from backend.mariadb import MariaDBConfig
from compute.backend_product import BackendProduct
from compute.backend_target import BackendTarget
from compute.node import Node

from ..abstract_backend import AbstractBackend
from ..base_backend import SingleUnManagedBackend
from ..base_mysql_backend import BaseMySqlBackend

MARIADB_CONFIG_FILE = "mariadb.yaml"


class SkySQLMariaDB(SingleUnManagedBackend, BaseMySqlBackend, AbstractBackend):
    """SkySQLclass for MariaDB"""

    clustered = False
    product = BackendProduct.mariadb

    kind = "mariadb"  # This is SkySQL default type for MariaDB, see SkySQLDeployment

    def __init__(
        self,
        node: Node,
        **kwargs,
    ):

        SingleUnManagedBackend.__init__(
            self,
            node=node,
            backend_config_yaml_file=MARIADB_CONFIG_FILE,
            backend_config_klass=MariaDBConfig,
        )
        bt_target = self.config.db
        bt_target.host = node.vm.network.get_public_iface()
        BaseMySqlBackend.__init__(self, bt=self.config.db)

    def install(self) -> "BackendTarget":
        return self.config.db

    def create_database_and_user_stmt(self) -> str:
        mysql_cmd = f"""
        create database if not exists {self.config.db.database};
        create user if not exists '{self.config.db.user}'@'%' identified by '{self.config.db.password}';
        GRANT ALTER, ALTER ROUTINE, CREATE, CREATE ROUTINE, CREATE TEMPORARY TABLES, CREATE USER, CREATE VIEW, DELETE, DROP, EXECUTE, INDEX, INSERT, LOCK TABLES, PROCESS, RELOAD, SELECT, SHOW DATABASES, SHOW VIEW, TRIGGER, UPDATE ON *.* TO '{self.config.db.user}'@'%';
        flush privileges;
        """
        return mysql_cmd

    def clean(self):
        pass

    def configure(self):
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
