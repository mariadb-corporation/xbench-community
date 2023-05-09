from abc import ABCMeta, abstractmethod

from compute import BackendTarget, Node


class AbstractDriver(metaclass=ABCMeta):
    @abstractmethod
    def __init__(self, node: Node, **kwargs):
        pass

    @abstractmethod
    def configure(self):
        pass

    @abstractmethod
    def install(self):
        pass

    @abstractmethod
    def self_test(self, bt: BackendTarget):
        pass
