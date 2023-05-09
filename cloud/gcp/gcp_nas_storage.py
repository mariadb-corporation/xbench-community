import dataclasses
import json
import logging
from enum import Enum
from typing import Dict, Optional

from cloud import VirtualMachine
from dacite import from_dict

from compute.node import Node

from ..abstract_storage import AbstractStorage
from ..virtual_storage import VirtualStorage
from .gcp_cli import GcpCli
from .exceptions import GcpCliException, GcpStorageException
from ..exceptions import CloudCliException, CloudStorageException

@dataclasses.dataclass
class GcpNasVirtualStorage(VirtualStorage):
    tier: str = "BASIC_HDD"
    ip: str = ""

    @property
    def is_shared(self) -> bool:
        return True

class GcpNasStorage(AbstractStorage[GcpCli, GcpNasVirtualStorage]):
    @property
    def instance_name(self):
        return f"{self.cluster_name}-{self.vs.name}" # storage instance name

    def update_vs(self, volume_spec: Dict):
        self.vs.id = volume_spec.get("name", "")
        self.vs.ip = volume_spec.get("networks", [])[0].get("ipAddresses", [])[0]

    def create(self) -> GcpNasVirtualStorage:
        cmd = """filestore instances create 
        %s 
        --file-share=capacity=%sTB,name=%s 
        --network=name=default 
        --zone=%s 
        --labels=tags=%s 
        """ % (
            self.instance_name, # storage instance name
            self.vs.size,
            self.vs.name, # volume name
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
        cmd = """filestore instances describe 
        %s 
        --zone=%s 
        --quiet 
        """ % (
            self.instance_name, # storage instance name
            self.vs.zone,
        )

        try:
            stdout_str, stderr_str, returncode = self.cli.run(cmd)
            self.logger.debug(f"Gcp returned {stdout_str}")
            return json.loads(stdout_str)
        except CloudCliException as e:
            if "NOT_FOUND" in str(e):
                raise GcpStorageException(f"Filestore instance {self.instance_name} does not exists")
            else:
                raise

    def destroy(self):
        try:
            self.describe()
        except (GcpStorageException, CloudStorageException) as e:
            self.logger.warn(e)
        else:
            cmd = """filestore instances delete 
            %s 
            --zone=%s 
            --quiet 
            """ % (
                self.instance_name, # storage instance name
                self.vs.zone,
            )

            stdout_str, stderr_str, returncode = self.cli.run(cmd)
            self.logger.debug(f"Gcp returned {stdout_str}")
            self.vs.id = ""

            return self.vs

    def attach_storage(self, vm: VirtualMachine):
        storage_ip = self.vs.ip
        mount_path = self.vs.device
        volume_name = self.vs.name
        cmd =f"""mkdir -p {mount_path} && 
        yum install nfs-utils -y && 
        mount {storage_ip}:/{volume_name} {mount_path} &&
        chmod go+rw {mount_path}
        """

        node = Node(vm)
        _ = node.run(cmd, timeout=600, sudo=True)
        self.logger.info(f"Mounted storage {storage_ip}:/{volume_name} at {mount_path} on VM {vm.name}")

    def detach_storage(self, vm: VirtualMachine):
        mount_path = self.vs.device
        cmd =f"umount {mount_path}"

        node = Node(vm)
        _ = node.run(cmd, timeout=600, sudo=True, ignore_errors=True)
        self.logger.info(f"Unmounted storage at {mount_path} on VM {vm.name}")
