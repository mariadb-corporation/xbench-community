# -*- coding: utf-8 -*-
# Copyright (C) 2022 dvolkov


from abc import ABC, abstractmethod
import dataclasses
import logging
from typing import Dict, Generic, Optional, Type, TypeVar, cast, final

from cloud import VirtualMachine
from cloud.exceptions import CloudStorageException
from dacite import from_dict

from .abstract_cli import AbstractCli
from .virtual_storage import VirtualStorage

T = TypeVar('T', bound=Optional[AbstractCli])
S = TypeVar('S', bound=VirtualStorage)

class AbstractStorage(ABC, Generic[T, S]):
    def __init__(self, cli: T, vs: VirtualStorage, **kwargs):
        """Initiate cloud storage
        """
        self.logger = logging.getLogger(self.__class__.__name__)

        self.cli = cli
        self.cluster_name = cli.cluster_name # type: ignore
        #
        t = self.__class__.__orig_bases__[0].__args__[1] # type: ignore
        self.vs: S = self._convert_type(t, vs)
        self.tag = f"{self.cluster_name}-{self.vs.name}"

    def as_dict(self):
        return dataclasses.asdict(self.vs)

    @property
    def volume_id(self):
        if self.vs.id is None:
            raise CloudStorageException("volume is not ready!  It must first be created")
        return self.vs.id

    def update_vs(self, volume_spec: Dict):
        """Updates `self.vs` from the `volume_spec`.
        """

    @final
    def create_safely(self) -> S:
        """Returns either the existing instance or newly created one.
        """
        try:
            volume_spec = self.describe()
            self.update_vs(volume_spec)
            return self.vs

        except CloudStorageException as e:
            return self.create()

    @abstractmethod
    def create(self) -> S:
        """Create volume with requested type, size, IOPS"""

    @abstractmethod
    def describe(self) -> Dict:
        """Describe the storage

        Returns:
            dict: dict with all storage attributes
        """

    def attach_storage(self, vm: VirtualMachine):
        """Attach volume to the instance"""

    def detach_storage(self, vm: VirtualMachine):
        """Detach Storage from instance"""

    @abstractmethod
    def destroy(self):
        """Destroy the volume"""

    def _convert_type(self, t: Type, val) -> S:
        dict = dataclasses.asdict(val)
        return from_dict(data_class=t, data=dict)
