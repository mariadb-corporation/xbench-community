# -*- coding: utf-8 -*-
# Copyright (C) 2021 dvolkov

import logging
from abc import ABC, abstractmethod
from multiprocessing import cpu_count
from typing import Dict, Generic, List, Optional, TypeVar, cast, final

from cloud.abstract_cli import AbstractCli
from cloud.abstract_compute import AbstractCompute
from cloud.cli_factory import CliFactory
from cloud.cloud_types import CloudTypeEnum
from cloud.compute_factory import ComputeFactory
from cloud.exceptions import CloudException
from cloud.storage_factory import StorageFactory
from cloud.virtual_machine import VirtualMachine
from cloud.virtual_storage import VirtualStorage
from compute import Node, run_parallel, run_parallel_returning

T = TypeVar("T", bound=Optional[AbstractCli])
C = TypeVar("C", bound=Optional[AbstractCompute])
P = TypeVar("P", Node, Dict)


class AbstractCloud(ABC, Generic[T, C]):

    """
    This indicates if we are deploying to long-lived instances.  With most clouds, the instances
    are not long-lived and can be created and destroyed as needed. However, in colo  environments,
    the machines persist and cannot be destroyed and recreated because they are physical hardware
    or we don't have the means to programmatically create and destroy them.
    """

    is_persistent: bool = False

    def __init__(self, cluster_name: str, **kwargs) -> None:
        """Initiate the cloud
        Expect to get the keys from impl.yaml
        Args:
            cluster_name (str): cluster name
            kwargs: cloud region config

        """
        self.cluster_name = cluster_name
        self.logger = logging.getLogger(self.__class__.__name__)
        self.cpu_count = cpu_count() - 1

        cloud_type = self.cloud_type()
        c = CliFactory().create_cli(cloud_type, cluster_name, **kwargs)
        # The cast silences mypy design-time error.
        # Mypy checker doesn't understand that 'T' definition is compatible with the create_cli() return type.
        self._cli: T = cast(T, c)

    @abstractmethod
    def cloud_type(self) -> CloudTypeEnum:
        """Gets the type of the cloud."""

    @final
    @property
    def cli(self) -> T:
        """Gets the CLI instance for the cloud."""
        return self._cli

    def is_running(self) -> bool:
        """Check to see if a given cloud has resources that it provisioned
        that are already running"""

        if self.cli is None:
            return False

        instances: list[dict] = self.cli.describe_instances_by_tag()
        if len(instances) > 0:
            return True
        return False

    def launch_instances(self, instances: List[Dict]) -> List[Optional[Node]]:
        """Launch similar instances in the cloud

        Returns:
            List[Node]: List of Nodes
        """
        return run_parallel_returning(instances, self.launch_instance)

    def terminate_instances(
        self, instances: List[Node], terminate_storage: bool = True
    ):
        """Terminate instances in the cloud

        Args:
            instances (List): List of instances to terminate
        """
        fn_log = lambda result: self.logger.debug(
            f"Instance {result} and its storage has been terminated"
        )
        run_parallel(instances, fn_log, self.terminate_instance, terminate_storage)

    def launch_instance(self, **instance_params) -> Optional[Node]:
        """Launch a single instance

        Returns:
            Node: Node object (which can do ssh for example!)
        """
        try:
            gc = ComputeFactory().create_compute(self.cli, **instance_params)

            vm = gc.create()
            self._process_storage(self.launch_storage, vm, **instance_params)

            return Node(vm)
        except CloudException as e:
            self.logger.error(e)
            return None

    def terminate_instance(self, instance: Node, terminate_storage: bool = False):
        gc = ComputeFactory().create_compute_from_vm(cli=self.cli, vm=instance.vm)
        gc.destroy()
        self._process_storage(
            self.detach_storage,
            instance.vm,
            terminate_storage=terminate_storage,
            **{"instance_type": instance.vm.instance_type},
        )

    def launch_storage(
        self,
        attach_to_vm: Optional[VirtualMachine],
        storage_params: VirtualStorage,
        **kwargs,
    ) -> Optional[VirtualStorage]:

        try:
            virtual_storage = None
            if storage_params is not None:
                gs = StorageFactory().create_storage(
                    self.cli, storage_params, attach_to_vm, **kwargs
                )
                virtual_storage = gs.create()
                if attach_to_vm is not None:
                    gs.attach_storage(attach_to_vm)

            return virtual_storage
        except CloudException as e:
            self.logger.error(e)
            return None

    def launch_storage_instances(
        self, storage_list: List[VirtualStorage], **kwargs
    ) -> List[VirtualStorage]:
        return self._process_storage_instances(
            self.launch_storage, None, storage_list, **kwargs
        )

    def terminate_storage_instances(
        self, storage_list: List[VirtualStorage], **kwargs
    ) -> List[VirtualStorage]:
        return self._process_storage_instances(
            self.terminate_storage, None, storage_list, **kwargs
        )

    def detach_storage(
        self,
        vm: VirtualMachine,
        storage: VirtualStorage,
        terminate_storage: bool = False,
        **kwargs,
    ) -> VirtualStorage:
        gs = StorageFactory().create_storage(self.cli, storage, vm, **kwargs)
        # _ = gs.detach_storage(vm)
        if terminate_storage and not storage.is_shared:
            gs.destroy()

        return gs.vs

    def terminate_storage(self, _, storage: VirtualStorage, **kwargs) -> VirtualStorage:
        gs = StorageFactory().create_storage(self.cli, storage, None, **kwargs)
        gs.destroy()

        return gs.vs

    def _process_storage(self, fn, vm: VirtualMachine, **kwargs):
        if vm.storage is not None:
            vm.storage = fn(vm, vm.storage, **kwargs)

        if vm.storage_list is not None:
            vm.storage_list = self._process_storage_instances(
                fn, vm, vm.storage_list, **kwargs
            )

    def _process_storage_instances(
        self,
        fn,
        vm: Optional[VirtualMachine],
        storage_list: List[VirtualStorage],
        /,
        **kwargs,
    ) -> List[VirtualStorage]:
        virtual_storage_list: list[VirtualStorage] = []
        if storage_list:
            for s in storage_list:
                ps = fn(vm, s, **kwargs)
                virtual_storage_list.append(ps if ps is not None else s)
        return virtual_storage_list

    def stop_instance(self, instance: Node):
        gc = ComputeFactory().create_compute_from_vm(cli=self.cli, vm=instance.vm)
        gc.stop()

    def stop_instances(self, instances: list[Node]):
        """stop and shutdown instances in the cloud

        Args:
            instances (List): List of instances to stop
        """

        def noop(x):
            return x

        run_parallel(instances, noop, self.stop_instance)

    def start_instance(self, instance: Node, **kwargs) -> Node:
        gc = ComputeFactory().create_compute_from_vm(cli=self.cli, vm=instance.vm)
        vm = gc.start()
        return Node(vm)

    def start_instances(self, instances: list[Node]) -> List[Optional[Node]]:
        """start and boot up instances in the cloud

        Args:
            instances (List): List of instances to start
        Return: list of instances started (their attributes could be slightly different)
        """

        return run_parallel_returning(instances, self.start_instance)
