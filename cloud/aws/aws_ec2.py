# Attach volume to the instance
# https://github.com/GoogleCloudPlatform/PerfKitBenchmarker/blob/2bb427083c4cf46fddc8e06fadec79937dfa66a2/perfkitbenchmarker/providers/aws/aws_disk.py

# -*- coding: utf-8 -*-
# Copyright (C) 2022 dvolkov


import dataclasses
import json
import logging
from dataclasses import asdict
from enum import Enum
from typing import Dict, Optional

from dacite import from_dict

from cloud.virtual_network import VirtualNetwork

from ..abstract_compute import AbstractCompute
from ..exceptions import CloudCliException
from ..virtual_machine import VirtualMachine
from .aws_cli import AwsCli
from .exceptions import AwsCliException, AwsEc2Exception


# TODO: add a creator tag to each instance
class AwsEc2(AbstractCompute):
    def __init__(self, cli: AwsCli, **kwargs):
        self.logger = logging.getLogger(__name__)

        self.cli = cli
        self.cluster_name = cli.cluster_name
        # Placement group requires some massaging.
        # I am going to inject group name from cloud to the VM parameters
        self.use_placement_group = kwargs.get("use_placement_group")
        # I need to get the name from cloud level or cli
        placement_group_dict = (
            {"placement_group": self.cli.placement_group}
            if self.use_placement_group
            else {"placement_group": None}
        )
        # Creating VM
        self.vm = from_dict(
            data_class=VirtualMachine,
            data=kwargs
            | {"cluster_name": self.cluster_name, "cloud": "aws"}
            | placement_group_dict,
        )
        self.tag = f"{self.cluster_name}-{self.vm.name}"

    @property
    def instance_id(self):
        if self.vm.id is None:
            raise AwsEc2Exception("Instance is not ready. Id must be created first")
        return self.vm.id

    @classmethod
    def from_vm(cls, cli: AwsCli, vm: VirtualMachine):
        return cls(cli, **dataclasses.asdict(vm))

    @classmethod
    def from_defaults(cls, cli: AwsCli, **kwargs):
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

    def aws_managed(self) -> bool:
        return (
            True if self.instance_id.startswith("i-") else False
        )  # This is AWS format

    def as_dict(self):
        return dataclasses.asdict(self.vm)

    def create(self) -> VirtualMachine:

        try:
            subnet_id = self.cli.region_config.get("zones", None)[self.vm.zone]
            image_id = self.cli.region_config.get("images", None)[self.vm.os_type][
                self.vm.arch
            ]["image_id"]

            security_group = self.cli.region_config.get("security_group")
            key_name = self.cli.region_config.get("key_name")
            self.vm.key_file = (
                self.cli.region_config.get("key_file", None)
                if self.vm.key_file == ""
                else self.vm.key_file
            )
            self.vm.ssh_user = self.cli.region_config.get("images", None)[
                self.vm.os_type
            ][self.vm.arch]["ssh_user"]

        except KeyError as e:
            raise AwsEc2Exception(f"problem with configuration: {e}")

        # Ingesting placement group if requested
        placement_group_clause = (
            f"--placement GroupName={self.vm.placement_group}"
            if self.vm.placement_group
            else ""
        )

        try:
            cmd = f"""ec2 run-instances
            --output json
            --count 1
            --instance-type {self.vm.instance_type}
            --image-id {image_id}
            --key-name {key_name}
            --subnet-id {subnet_id}
            {placement_group_clause}
            --security-group-ids {security_group}
            --block-device-mappings DeviceName=/dev/sda1,Ebs={{DeleteOnTermination=true}}
            """

            # I need substitute differently because f-string doesn't work
            tag = """ --tag-specifications
            'ResourceType=instance,Tags=[{Key=Name,Value=%s}]'
            """ % (
                self.tag,
            )

            # Final command + jq filter
            final_cmd = cmd + tag + "| jq '.Instances[] | {id: .InstanceId}' | jq -s"
            self.logger.debug(final_cmd)
            self.logger.debug(f"Starting instance creation")
            (stdout_str, stderr_str, returncode,) = self.cli.run(
                " ".join(final_cmd.split())
            )  # Produced array of dict with keys id,ip,name

            self.logger.debug(f"Aws returned {stdout_str} {stderr_str}")

            instance = json.loads(stdout_str)  # this is a list of dict
            self.vm.id = instance[0].get("id")

            # I need to wait to get public ip address
            self.wait_for_instance(self.cli.ComputeState.running)
            # Now I am ready to see public IPs
            instance = self.describe()
            self.vm.network = VirtualNetwork(
                public_ip=instance.get("public_ip", ""),
                private_ip=instance.get("private_ip", ""),
            )
            # if self.vm.network:
            #    self.vm.network.public_ip = instance.get("public_ip", "")
            #    self.vm.network.private_ip = instance.get("private_ip", "")
            return self.vm
            # Return Virtual Machines
        except CloudCliException as e:
            raise AwsEc2Exception(f"aws command failed with {e}")

    def wait_for_instance(self, wait_for_status: AwsCli.ComputeState):
        """[summary]

        Args:
            instance_ids (List): [description]
        """
        self.logger.debug(
            f"Waiting until {self.vm.name} ({self.instance_id}) is in status"
            f" {wait_for_status}"
        )
        try:
            self.cli.wait_for_instance(self.instance_id, wait_for_status)
            self.logger.debug(
                f"{self.vm.name} ({self.instance_id}) is in {wait_for_status}"
            )
        except CloudCliException as e:
            if "InvalidInstanceID.Malformed" in str(e):
                self.logger.warn(e)
            else:
                AwsEc2Exception(e)

    def describe(self) -> Dict:
        """
        Args:
            instance_ids (List): [description]
        Returns: Dict: with important instance(s) information
        """
        cmd = f"ec2 describe-instances --output json --instance-ids {self.instance_id}"

        # This assumes a single tag per resource
        # use | jq  '.Reservations[].Instances[] | {id: .InstanceId, private_ip: .PrivateIpAddress, public_ip: .PublicIpAddress, tags: .Tags} '  | jq -s
        # for multiple tags

        # TODO add volume  ID
        # BlockDeviceMappings[*].Ebs.VolumeId
        final_cmd = (
            cmd
            + " | jq  '.Reservations[].Instances[] | {id: .InstanceId, private_ip:"
            " .PrivateIpAddress, public_ip: .PublicIpAddress, name: .Tags[].Value}' |"
            " jq -s"
        )
        try:
            stdout_str, stderr_str, returncode = self.cli.run(final_cmd)
            self.logger.debug(f"Aws returned {stdout_str}")
            instances = json.loads(stdout_str)

        except CloudCliException as e:
            if "InvalidInstanceID.NotFound" in str(e):
                raise AwsEc2Exception(f"Instance {self.vm.id} does not exist")
            else:
                raise AwsCliException(f"aws command failed with {e}")
        else:
            if len(instances) == 0:
                raise AwsEc2Exception(f"Instance {self.instance_id} doesn't exist")
            else:
                return instances[0]

    def configure(self, **kwargs) -> tuple[VirtualMachine, Optional[str]]:
        raise Exception("not implemented")

    def destroy(self):
        """[summary]
        https://awscli.amazonaws.com/v2/documentation/api/latest/reference/ec2/terminate-instances.html
        """

        # Some instances could be self-managed
        if self.aws_managed():  # This is AWS format

            # Terminate waits forewer if instance doesn't exist
            try:
                self.describe()
            except AwsEc2Exception as e:
                self.logger.error(f"Instance {self.instance_id} doesn't exist")
            else:
                self.cli.terminate_instance(self.instance_id)
                # instance-terminated
                self.logger.info(
                    f"{self.vm.name} ({self.instance_id}) submitted for termination"
                )
                self.wait_for_instance(wait_for_status=self.cli.ComputeState.terminated)
                self.logger.info(
                    f"{self.vm.name} ({self.instance_id}) has been terminated"
                )
        else:
            self.logger.warning("Instance is self managed")

    def reboot(self, wait: bool = True):
        if self.aws_managed():
            cmd = f"ec2 reboot-instances --instance-ids {self.instance_id}"
            _, _, _ = self.cli.run(cmd)
            self.logger.info(f"Instance {self.instance_id} submitted for reboot")
            if wait:
                self.wait_for_instance(self.cli.ComputeState.running)
            self.logger.info(f"Instance {self.instance_id} has been rebooted")
        else:
            self.logger.warning("Instance is self managed")

    def stop(self):
        if self.aws_managed():  # This is AWS format
            cmd = f"ec2 stop-instances --instance-ids {self.instance_id}"
            _, _, _ = self.cli.run(cmd)
            self.logger.info(f"Instance {self.instance_id} submitted to stop")
            self.wait_for_instance(self.cli.ComputeState.stopped)
            self.logger.info(f"Instance {self.instance_id} has been stopped")
        else:
            self.logger.warning("Instance is self managed")

    def start(self) -> Optional[VirtualMachine]:
        if self.aws_managed():  # This is AWS format
            cmd = f"ec2 start-instances --instance-ids {self.instance_id}"
            _, _, _ = self.cli.run(cmd)
            self.logger.info(f"Instance {self.instance_id} submitted to start")
            self.wait_for_instance(self.cli.ComputeState.running)
            self.logger.info(f"Instance {self.instance_id} has started")
            instance = self.describe()
            self.vm.network = VirtualNetwork(
                public_ip=instance.get("public_ip", ""),
                private_ip=instance.get("private_ip", ""),
            )
            return self.vm
        else:
            self.logger.warning("Instance is self managed")
            return None
