# -*- coding: utf-8 -*-
# Copyright (C) 2021 dvolkov

from abc import ABCMeta, abstractmethod
from typing import List, Union

from compute import BackendTarget, Node


class AbstractProxy(metaclass=ABCMeta):
    @abstractmethod
    def __init__(
        self,
        nodes: Union[List[Node], Node],
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
    def install(self):
        pass

    @abstractmethod
    def post_install(self, bt: BackendTarget) -> BackendTarget:
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
