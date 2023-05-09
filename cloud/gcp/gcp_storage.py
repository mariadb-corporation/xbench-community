import dataclasses
import json
import logging
from enum import Enum
from typing import Dict, Optional

from cloud import VirtualMachine
from compute.node import Node
from dacite import from_dict

from ..abstract_storage import AbstractStorage
from ..virtual_storage import VirtualStorage
from .exceptions import GcpCliException, GcpStorageException
from ..exceptions import CloudCliException
from .gcp_cli import GcpCli


class GcpStorage(AbstractStorage[GcpCli, VirtualStorage]):
    def __init__(self, cli: GcpCli, vs: VirtualStorage, **kwargs):
        super(GcpStorage, self).__init__(cli, vs, **kwargs)

        self.vm_name = kwargs.get("vm_name", "")
        self.tag = f"{self.cluster_name}"

    @property
    def instance_name(self):
        vm_suffix = f"{self.vm_name}-" if self.vm_name is not None else ""
        return f"{self.cluster_name}-{vm_suffix}{self.vs.name}" # storage instance name

    def update_vs(self, volume_spec: Dict):
        self.vs.id = volume_spec[0].get("id")

    def create(self) -> VirtualStorage:
        cmd = """compute disks create
        %s
        --type=%s
        --size=%s
        --zone=%s
        --labels=tags=%s
        """ % (
            self.instance_name,
            self.vs.type,
            self.vs.size,
            self.vs.zone,
            self.tag,
        )

        stdout_str, stderr_str, returncode = self.cli.run(cmd)
        self.logger.debug(f"Gcp returned {stdout_str}")
        volume_spec = json.loads(stdout_str)
        self.logger.debug(f"Volume: {volume_spec}")

        self.update_vs(volume_spec)

        return self.vs

    def describe(self) -> Dict:
        cmd = """compute disks describe
        %s
        --zone=%s
        """ % (
            self.vs.id if self.vs.id != "" else self.instance_name, # disk name or id
            self.vs.zone,
        )

        try:
            stdout_str, stderr_str, returncode = self.cli.run(cmd)
            self.logger.debug(f"Gcp returned {stdout_str}")
            return json.loads(stdout_str)
        except CloudCliException as e:
            if "HTTPError 404" in str(e):
                raise GcpStorageException(f"Disk instance {self.instance_name} does not exists")
            else:
                raise

    def destroy(self):
        try:
            self.describe()
        except GcpStorageException as e:
            self.logger.warn(e)
        else:
            cmd = """compute disks delete
            %s
            --zone=%s
            --quiet
            """ % (
                self.vs.id, # disk name or id
                self.vs.zone,
            )

            stdout_str, stderr_str, returncode = self.cli.run(cmd)
            self.logger.debug(f"Gcp returned {stdout_str}")
            self.vs.id = ""

            return self.vs

    def attach_storage(self, vm: VirtualMachine):
        # TODO Google would mount requested device to its own name
        # This function should return real device name
        #ls -l /dev/disk/by-id
        # lrwxrwxrwx. 1 root root  9 Aug 23 19:22 google-persistent-disk-0 -> ../../sda
        # lrwxrwxrwx. 1 root root 10 Aug 23 19:22 google-persistent-disk-0-part1 -> ../../sda1
        # lrwxrwxrwx. 1 root root 10 Aug 23 19:22 google-persistent-disk-0-part2 -> ../../sda2
        # lrwxrwxrwx. 1 root root  9 Aug 23 19:27 google-xvdb -> ../../sdb

        cmd = """compute instances attach-disk
        %s
        --disk=%s
        --zone=%s
        --device-name=%s
        """ % (
            vm.id,
            self.vs.id,
            vm.zone,
            self.vs.device
        )

        _, _, _ = self.cli.run(cmd)
        self.vs.device = f"/dev/{self.vs.device}" # TODO ^^
        self.logger.debug(f"Volume {self.vs.id} attached to VM {vm.id}")

    def detach_storage(self, vm: VirtualMachine):
        cmd = """compute instances detach-disk
        %s
        --disk=%s
        --zone=%s
        """ % (
            vm.id,
            self.instance_name,
            vm.zone,
        )

        _, _, _ = self.cli.run(cmd)
        self.logger.debug(f"Volume {self.vs.id} detached to VM {vm.id}")
