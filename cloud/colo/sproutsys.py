import logging
import os
import socket
from multiprocessing import cpu_count
from pathlib import Path
from queue import Queue
from typing import Optional

import pid
import yaml
from cloud.exceptions import CloudException
from common.common import shuffle_list_inplace
from compute import Node
from lib import XbenchConfig

from ..abstract_cloud import AbstractCloud
from ..cloud_types import CloudTypeEnum
from .exceptions import ColoCloudEx, ColoCloudProvisioningEx
from .sproutsys_cli import SproutsysCLI

COLO_CONFIG_FILE = "colo.yaml"
ORCHESTRATION_HOST = "vqc008d.colo.sproutsys.com"
XBENCH_PID_DIR = "/var/run"  # to prevent multiple invocations
XBENCH_PID_FILE = "xbench.pid"
XBENCH_LOCK_FILE = "/var/lock/xbench.lock"  # Hosts are currently in use


class Sproutsys(AbstractCloud[SproutsysCLI, None]):

    is_persistent = True

    def __init__(self, cluster_name: str, **kwargs):
        super(Sproutsys, self).__init__(cluster_name, **kwargs)
        self.cluster_name = cluster_name
        self.logger = logging.getLogger(self.__class__.__name__)
        self.cpu_count = cpu_count() - 1
        self.colo_hosts_file_path = os.path.join(
            XbenchConfig().config_dir, COLO_CONFIG_FILE
        )
        self._create_lock_file()
        self.host_list: Queue[str] = Queue()
        self._host_list = self._parse_host_list(self.colo_hosts_file_path)
        self._region = kwargs.get("region")
        self.available_hosts = [
            host
            for host in self._host_list[self._region]
            if not self._node_is_locked(host)
        ]
        self._populate_hosts()
        self.logger.info(
            f"Sproutsys cloud initialized with {self.available_hosts} available hosts"
        )

        if socket.gethostname() != ORCHESTRATION_HOST:
            raise ColoCloudEx(
                f"The colo cloud can only be run from {ORCHESTRATION_HOST}."
            )

    def cloud_type(self) -> CloudTypeEnum:
        return CloudTypeEnum.Colo

    @staticmethod
    def _create_lock_file():
        Path(XBENCH_LOCK_FILE).touch()

    @staticmethod
    def _check_host_list_file(hosts: dict):
        """
        ensure that a host is not duplicated (in more than one region)
        """
        for region in hosts:
            other_regions: list[str] = [reg for reg in hosts.keys() if reg != region]
            for host in hosts[region]:
                for check_region in other_regions:
                    if host in hosts[check_region]:
                        raise ColoCloudEx(
                            f"Found '{host}' duplicated in {COLO_CONFIG_FILE} in both"
                            f" '{region}' and '{check_region}'"
                        )

    def _parse_host_list(self, host_list_file: str):
        with open(host_list_file, "r") as f:
            y = yaml.safe_load(f)
            self._check_host_list_file(y)
            return y

    def _populate_hosts(self):
        """
        Populate class level Queue
        """
        if self.available_hosts:
            for host in shuffle_list_inplace(self.available_hosts):
                self.host_list.put(item=host)

    def is_running(self) -> bool:
        with open(XBENCH_LOCK_FILE) as f:
            for line in f.readlines():
                if self.cluster_name in line:
                    self.logger.error(
                        f"Found '{line}' host in {XBENCH_LOCK_FILE} meaning that the"
                        " cluster may already be deployed."
                    )
                    return True
        return False

    def _check_node_availability(self, count: int, kind: str):
        """
        check that there are enough available hosts for a given instance type
        for example:
        if we request a count of 12 'yang' machines
        where 'yang' is the instance_type
        we need to see if that is possible
        by checking the host list file for the number of machines
        that match that instance_type
        """
        self.logger.debug(
            f"Checking for availability of '{kind}' instances.  Requested {count}"
        )
        available: int = 0
        for host in self.available_hosts:
            if kind in host:
                available += 1
        self.logger.debug(f"Found {available} nodes for '{kind}' instances")
        if count > available:
            raise ColoCloudProvisioningEx(
                f"Not enough host available.  Requested {count} '{kind}' instances, but"
                f" {available} are available.  Check your inventory file at"
                f" {self.colo_hosts_file_path} or the currently in-use nodes at"
                f" {XBENCH_LOCK_FILE}"
            )

    def _node_is_locked(self, node: str) -> bool:
        with open(XBENCH_LOCK_FILE) as f:
            for host_line in f.readlines():
                if node in host_line:
                    self.logger.warning(
                        f"Node '{node}' is locked in {XBENCH_LOCK_FILE}"
                    )
                    return True
        return False

    def _get_host_for_instance(self, instance: dict) -> dict:
        if self.host_list.empty():
            raise ColoCloudProvisioningEx(
                f"No hosts available left to provision '{instance.get('name')}' for"
                f" instance type '{instance.get('instance_type')}'.  Check your config"
                f" for '{instance.get('region')}' at {self.colo_hosts_file_path}"
            )
        self._check_node_availability(
            instance.get("count"), instance.get("instance_type")
        )
        maybe_host: str = self.host_list.get()
        instance["colo_host"] = maybe_host
        self.logger.debug(
            f"Attempting to provision '{maybe_host}' for '{instance.get('name')}'"
        )
        if (
            instance.get("instance_type") == "*"
            or instance.get("instance_type") in maybe_host
        ):
            return instance
        else:
            self.host_list.put(maybe_host)
            return self._get_host_for_instance(instance)

    def launch_instances(self, instances: list[dict]) -> list[Optional[Node]]:
        try:
            with pid.PidFile(pidname=XBENCH_PID_FILE, piddir=XBENCH_PID_DIR):
                for instance in instances:
                    instance = self._get_host_for_instance(instance)
                    self.logger.info(f"attempting to lock host {instance['colo_host']}")
                    with open(XBENCH_LOCK_FILE, "a") as f:
                        f.write(f"{instance['colo_host']}-{self.cluster_name}\n")

            return super(Sproutsys, self).launch_instances(instances)
        except pid.PidFileAlreadyLockedError:
            raise CloudException("Xbench is already running.  Try again later")

    def launch_instance(self, **instance_params) -> Optional[Node]:
        return self.cli.deploy_host(instance_params.get("colo_host"), instance_params)

    def terminate_instances(
        self, instances: list[Node], terminate_storage: bool = True
    ):
        try:
            with pid.PidFile(pidname=XBENCH_PID_FILE, piddir=XBENCH_PID_DIR) as p:
                with open(XBENCH_LOCK_FILE, "r") as cur_f:
                    other_hosts: list[str] = [
                        host
                        for host in cur_f.readlines()
                        if self.cluster_name not in host
                    ]
                self.logger.info(
                    f"attempting to unlock hosts for cluster {self.cluster_name}"
                )
                with open(XBENCH_LOCK_FILE, "w") as new_f:
                    new_f.writelines(other_hosts)
                return super(Sproutsys, self).terminate_instances(
                    instances, terminate_storage
                )
        except pid.PidFileAlreadyLockedError:
            raise CloudException("Xbench is already running.  Try again later")

    def terminate_instance(self, instance: Node, terminate_storage: bool = False):
        """
        remove the host from the lock file

        option 1: call Provisioning.clean from deprovisioning ?
        - will I have to construct a Provisioning() instance in deprovisioning
        - call `clean` before we `install`
        option 2: call the Backend.clean ?
        - how do I get access to the backend class during deprovisioning
        - the backend class has to be constructed dynamically
        option 3: universal uninstaller ?
        - rm -rf /data and try to stop all possibly installed databases / benchmarks
        - maintain uninstallation behaviors in multiple places
        option 4: re-image the machine for a new OS ?
        - this might take too long
        - won't work or will work differently in different colos

        nuke functionality
        option 1: optimistically unlock, even if we don't know what happened during deprovision
        or we had an error.  We have to deal with problems during provisioning
        option 2: pessimistically lock.  We have to know what happens after deprovision to decide
        if the host can be unlocked or not.  We deal with all problems during provision
        option 3: nihilisticly unlock, accept all risks and re-image the OS, destroying current state
        """
        pass

    def stop_instances(self, instances: list[Node]):
        self.logger.warning("starting and stopping Sproutsys colo hosts is not supported")

    def start_instances(self, instances: list[Node]):
        self.logger.warning("starting and stopping Sproutsys colo hosts is not supported")
