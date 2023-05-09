from abc import ABCMeta, abstractmethod
from typing import Union

from compute import BackendTarget, Node
from compute.backend_dialect import BackendDialect
from compute.backend_product import BackendProduct


class AbstractBackend(metaclass=ABCMeta):

    clustered = False
    dialect = BackendDialect.mysql
    product = BackendProduct.mysql

    @abstractmethod
    def __init__(
        self,
        nodes: Union[list[Node], Node],
        **kwargs,
    ):
        """Backend constructor

        Args:
            nodes (Union[List[Node], Node]):
        """

    @abstractmethod
    def configure(self):
        pass

    @abstractmethod
    def install(self) -> BackendTarget:
        pass

    @abstractmethod
    def db_connect(self):
        pass

    @abstractmethod
    def self_test(self):
        pass

    @abstractmethod
    def clean(self):
        pass

    @abstractmethod
    def start(self, **kwargs):
        pass

    @abstractmethod
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

    @abstractmethod
    def print_db_size(self, database: str) -> None:
        pass

    def get_logs(self) -> str:
        pass
