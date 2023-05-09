# -*- coding: utf-8 -*-
# Copyright (C) 2022 dvolkov


import logging
from abc import ABCMeta, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Optional

from compute import ProcessExecutionException, RunSubprocess

from .exceptions import CloudCliException

CLI_DEFAULT_TIMEOUT = 600


@dataclass
class SecurityRecord:
    port_from: int
    port_to: int
    cidr: str
    name: Optional[str] = None  # GCP has name, but AWS doesn't
    desc: Optional[str] = "xbench self service"

    def __post_init__(self):
        """Add default subnet"""
        if "/" not in self.cidr:
            self.cidr += "/32"

    def __str__(self):
        return f"{self.cidr}:{self.port_from}:{self.port_to}:{self.name}:{self.desc}"


class AbstractCli(metaclass=ABCMeta):

    # You supposed to redefine string constants
    class ComputeState(str, Enum):
        running = "instance-running"
        terminated = "instance-terminated"
        stopped = "instance-stopped"

    class StorageState(str, Enum):
        ready = "volume-available"
        in_use = "volume-in-use"
        deleted = "volume-deleted"

    def __init__(self, cluster_name: str, **kwargs):
        """Class init method"""
        self.cluster_name = cluster_name
        self.logger = logging.getLogger(self.__class__.__name__)
        self.region_config = kwargs
        self._check_stderr = True

        allowed_keys = list(self.__dict__.keys())
        self.__dict__.update(
            (key, value) for key, value in kwargs.items() if key in allowed_keys
        )

        self.check_cli_version()

    @abstractmethod
    def check_cli_version(self):
        """Checks CLI version."""

    def get_base_command(self) -> str:
        """Gets base command string."""
        return ""

    def run(
        self,
        cmd: str,
        timeout: Optional[int] = CLI_DEFAULT_TIMEOUT,
        shell: bool = True,
        use_base_command: bool = True,
    ) -> tuple:
        """Execute cli command

        Args:
            cmd (str): _description_
            timeout (Optional[int]): _description_
            shell (bool, optional): _description_. Defaults to True.

        Returns: Tuple: Command stdout, stderr and status code.
        """
        if use_base_command:
            cmd = self.get_base_command() + " " + cmd
        cmd = " ".join(cmd.split())
        try:
            proc = RunSubprocess(cmd=cmd, timeout=timeout)
            if shell:
                (stdout, stderr, exit_code) = proc.run_as_shell()
            else:
                (stdout, stderr, exit_code) = proc.run()

            if exit_code != 0 or (self._check_stderr and len(stderr) > 0):
                raise CloudCliException(f"CLI command failed with {stderr}")
            return (stdout, stderr, exit_code)

        except ProcessExecutionException as e:
            raise CloudCliException(f"CLI command failed with {e}")

    @abstractmethod
    def describe_instances_by_tag(self) -> list[Dict]:
        """Return list of instances for the cluster

        Returns:
            list[Dict]: _description_
        """

    @abstractmethod
    def terminate_instances(self, instances: list[Dict]):
        """Terminated instances"""

    @abstractmethod
    def wait_for_instances(self, instances: list[Dict], instance_status: str):
        """Wait for status"""

    @abstractmethod
    def describe_volumes_by_tag(self) -> list[Dict]:
        """List of attached volumes per cluster"""

    @abstractmethod
    def delete_volumes(self, volumes: list[Dict]):
        """Delete attached volumes"""

    def list_security_access(self) -> List[SecurityRecord]:
        raise CloudCliException("list_security_access is not implemented")

    def authorize_access(self, rec: SecurityRecord):
        raise CloudCliException("authorize_access is not implemented")

    def revoke_access(self, rec: SecurityRecord):
        raise CloudCliException("revoke_access is not implemented")
