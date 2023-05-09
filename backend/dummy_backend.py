# -*- coding: utf-8 -*-
# Copyright (C) 2021 dvolkov

from typing import List, Union

from compute import BackendTarget, Node
from compute.backend_dialect import BackendDialect
from compute.backend_product import BackendProduct

from .abstract_backend import AbstractBackend


class SingleDummyBackend(AbstractBackend):

    clustered = False

class DummyBackend(AbstractBackend):

    clustered = True

    def __init__(
        self,
        nodes: Union[List[Node], Node],
        **kwargs,
    ):
        """Backend constructor

        Args:
            nodes (Union[List[Node], Node]):
        """

    def configure(self):
        pass

    def install(self) -> BackendTarget:
        pass

    def db_connect(self):
        pass

    def self_test(self):
        pass

    def clean(self):
        pass

    def start(self, **kwargs):
        pass

    def stop(self, **kwargs):
        pass

    def post_data_load(self, database: str):
        pass

    def pre_workload_run(self, **kwargs):
        pass

    def post_workload_run(self, **kwargs):
        pass

    def pre_thread_run(self, **kwargs):
        pass

    def print_db_size(self, database: str) -> None:
        pass
