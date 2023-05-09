# -*- coding: utf-8 -*-
# Copyright (C) 2022 dvolkov


import logging

from dacite import from_dict

from backend.base_backend import SingleUnManagedBackend
from backend.base_mysql_backend import BaseMySqlBackend
from backend.xpand.base_xpand_backend import BaseXpandBackend
from compute import BackendTarget, Node
from compute.backend_dialect import BackendDialect
from compute.backend_product import BackendProduct

from ..abstract_backend import AbstractBackend
from .externaldb_config import ExternalDBConfig

EXTERNAL_DB_CONFIG_FILE = "externaldb.yaml"


class ExternalMysqlDB(SingleUnManagedBackend, BaseMySqlBackend, AbstractBackend):
    """Generic External MySQL compatible Database (AWS Aurora as an example"""

    clustered = False
    dialect = BackendDialect.mysql
    product = BackendProduct.mysql

    def __init__(
        self,
        node: Node,
        **kwargs,
    ):
        self.logger = logging.getLogger(__name__)

        SingleUnManagedBackend.__init__(
            self,
            node=node,
            backend_config_yaml_file=EXTERNAL_DB_CONFIG_FILE,
            backend_config_klass=ExternalDBConfig,
            **kwargs,
        )
        self.config.db.host = node.vm.network.get_public_iface()
        BaseMySqlBackend.__init__(self, bt=self.config.db)

    def install(self) -> BackendTarget:
        return self.config.db

    def configure(self):
        pass

    def self_test(self):
        pass

    def clean(self):
        pass

    def start(self, **kwargs):
        pass

    def stop(self, **kwargs):
        pass


class ExternalXpand(SingleUnManagedBackend, BaseXpandBackend, AbstractBackend):
    """Generic External Xpand compatible Database (SkySQL as an example"""

    clustered = False

    def __init__(
        self,
        node: Node,
        **kwargs,
    ):
        self.logger = logging.getLogger(__name__)

        SingleUnManagedBackend.__init__(
            self,
            node=node,
            backend_config_yaml_file=EXTERNAL_DB_CONFIG_FILE,
            backend_config_klass=ExternalDBConfig,
            **kwargs,
        )
        self.config.db.host = node.vm.network.get_public_iface()
        BaseXpandBackend.__init__(self, bt=self.config.db)

    def install(self) -> BackendTarget:
        return self.config.db

    def configure(self):
        pass

    def self_test(self):
        pass

    def clean(self):
        pass

    def start(self, **kwargs):
        pass

    def stop(self, **kwargs):
        pass
