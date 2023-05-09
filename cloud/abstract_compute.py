# -*- coding: utf-8 -*-
# Copyright (C) 2022 dvolkov


from abc import ABCMeta, abstractmethod
from typing import Dict, Optional

from .abstract_cli import AbstractCli
from .virtual_machine import VirtualMachine


class AbstractCompute(metaclass=ABCMeta):
    @abstractmethod
    def __init__(self, cli: AbstractCli, **kwargs):
        """Class init method"""

    @abstractmethod
    def create(self) -> VirtualMachine:
        """Create a virtual machine"""

    def describe(self) -> Dict:
        """Describe the storage

        Returns:
            dict: dict with all storage attributes
        """
        pass

    def configure(self, **kwargs) -> tuple[VirtualMachine, Optional[str]]:
        """Provide some basic service"""
        pass

    @abstractmethod
    def destroy(self):
        """Destroy the VM"""

    def reboot(self, wait: bool = True):
        """Reboot the VMs
        wait (bool, optional): If wait then method will be waiting until instance in ready state. Defaults to True.
        """
        pass

    def start(self) -> Optional[VirtualMachine]:
        """Start the compute instance"""
        return None

    def stop(self):
        """Stop the compute instance"""
        pass
