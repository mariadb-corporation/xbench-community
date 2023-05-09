import dataclasses
import json
import logging
from typing import Dict, Optional

from dacite import from_dict

from cloud.virtual_network import VirtualNetwork

from ..abstract_compute import AbstractCompute
from ..exceptions import CloudCliException
from ..virtual_machine import VirtualMachine
from .exceptions import GcpCliException, GcpCloudException
from .gcp_cli import GcpCli


class GcpCompute(AbstractCompute):
    def __init__(self, cli: GcpCli, **kwargs):
        self.logger = logging.getLogger(__name__)

        self.cli = cli
        self.cluster_name = cli.cluster_name
        # Creating VM
        self.vm = from_dict(
            data_class=VirtualMachine,
            data=kwargs
            | {"cluster_name": self.cluster_name, "cloud": "gcp"}
        )
        self.tag = self.cluster_name

    @property
    def instance_id(self):
        if self.vm.id is None:
            raise GcpCloudException("Instance is not ready. Id must be created first")
        return self.vm.id

    @classmethod
    def from_defaults(cls, cli: GcpCli, **kwargs):
        defaults = {
            "id": "i-086b29dc402f383f2",
            "name": "name",
            "role": "role",
            "klass": "klass",
            "key_file": "my_file",
            "instance_type": "i3",
            "zone": "us-west-2",
            "os_type": "linux",
            "managed": True,
        }
        return cls(cli, **(defaults | kwargs))

    def is_managed(self) -> bool:
        return False

    def as_dict(self):
        return dataclasses.asdict(self.vm)

    def create(self) -> VirtualMachine:
        try:
            # subnet_id = self.cli.region_config.get("zones", None)[self.vm.zone]
            image = self.cli.region_config.get("images", None)[self.vm.os_type][
                self.vm.arch]


        except KeyError as e:
            raise GcpCloudException(f"problem with configuration: {e}")

        try:
            self.vm.key_file = (
                self.cli.region_config.get("key_file", None)
                if self.vm.key_file == ""
                else self.vm.key_file
            )
            self.vm.pub_file = (
                self.cli.region_config.get("pub_file", None)
                if self.vm.pub_file == ""
                else self.vm.pub_file
            )
            self.vm.ssh_user = self.cli.region_config.get("images", None)[
                self.vm.os_type][self.vm.arch]["ssh_user"]

            instances = self.cli.create(self.vm, image, [self.tag])

            instance = instances[0]
            self.vm.id = instance.get("id")
            # self.vm.name = instance.get("name")

            self.vm.network = VirtualNetwork(public_ip = instance.get("networkInterfaces")[0].get("accessConfigs")[0].get("natIP"),private_ip = instance.get("networkInterfaces")[0].get("networkIP"))
            #if self.vm.network:
            #    self.vm.network.public_ip = instance.get("networkInterfaces")[0].get("accessConfigs")[0].get("natIP")
            #    self.vm.network.private_ip = instance.get("networkInterfaces")[0].get("networkIP")

            return self.vm
            # Return Virtual Machines
        except CloudCliException as e:
            raise GcpCloudException(f"GCP command failed with {e}")

    def describe(self) -> Dict:
        zone_id = self.vm.zone
        cmd = f"""compute instances describe
        {self.instance_id}
        --zone {zone_id}
        """

        try:
            stdout_str, stderr_str, returncode = self.cli.run(cmd)
            self.logger.debug(f"GCP returned {stdout_str}")
            instance = json.loads(stdout_str)

        except CloudCliException as e:
            if "was not found" in str(e):
                raise GcpCloudException(f"Instance {self.vm.id} does not exist")
            else:
                raise GcpCliException(f"GCP command failed with {e}")
        else:
            return instance

    def configure(self, **kwargs) -> tuple[VirtualMachine, Optional[str]]:
        raise Exception("not implemented")

    def destroy(self):
        self.cli.terminate_instance(self.vm.id, self.vm.zone)

    def reboot(self, wait: bool = True):
        # There's no soft reboot in GCP, see:
        # https://cloud.google.com/compute/docs/instances/instance-life-cycle
        self.stop()
        self.start()

    def stop(self):
        zone_id = self.vm.zone
        cmd = f"""compute instances stop
        {self.instance_id}
        --zone {zone_id}
        """
        self.logger.info(f"Instance {self.instance_id} submitted to stop")
        _, _, _ = self.cli.run(cmd)
        self.logger.info(f"Instance {self.instance_id} has been stopped")

    def start(self):
        zone_id = self.vm.zone
        cmd = f"""compute instances start
        {self.instance_id}
        --zone {zone_id}
        """
        self.logger.info(f"Instance {self.instance_id} submitted to start")
        _, _, _ = self.cli.run(cmd)
        self.logger.info(f"Instance {self.instance_id} has started")
