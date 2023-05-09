# Attach volume to the instance
# https://github.com/GoogleCloudPlatform/PerfKitBenchmarker/blob/2bb427083c4cf46fddc8e06fadec79937dfa66a2/perfkitbenchmarker/providers/aws/aws_disk.py

# -*- coding: utf-8 -*-
# Copyright (C) 2022 dvolkov


import dataclasses
import json
import logging
from enum import Enum
from typing import Dict, Optional

from dacite import from_dict

from cloud import VirtualMachine

from ..abstract_storage import AbstractStorage
from ..exceptions import CloudCliException, CloudStorageException
from ..virtual_storage import VirtualStorage
from .aws_cli import AwsCli
from .exceptions import AwsCliException, AwsStorageException


class AwsEbs(AbstractStorage[AwsCli, VirtualStorage]):
    def __init__(self, cli: AwsCli, vs: VirtualStorage, **kwargs):
        super(AwsEbs, self).__init__(cli, vs, **kwargs)

        self.is_nitro_type = kwargs.get("is_nitro_type", True)
        self.instance_type = kwargs.get("instance_type")

    def create(self) -> VirtualStorage:
        cmd = """ec2 create-volume
        --volume-type %s
        --no-encrypted
        --availability-zone %s
        --size %s
        --tag-specifications 'ResourceType=volume,Tags=[{Key=Name,Value=%s}]'
        --no-multi-attach-enabled
        """ % (
            self.vs.type,
            self.vs.zone,
            self.vs.size,
            self.tag,
        )
        iops_spec = (
            " --iops %s" % (self.vs.iops) if self.vs.type in ["io1", "io2"] else ""
        )

        cmd += iops_spec
        stdout_str, stderr_str, returncode = self.cli.run(cmd)
        self.logger.debug(f"Aws returned {stdout_str}")
        volume_spec = json.loads(stdout_str)
        self.logger.debug(f"Volume: {volume_spec}")
        self.vs.id = volume_spec.get("VolumeId")
        self.wait_for_storage(self.cli.StorageState.ready)

        return self.vs

    def describe(self) -> Dict:
        if self.vs.id == "":
            raise CloudStorageException(
                f"Volume for device {self.vs.device} does not exist"
            )

        cmd = f"ec2 describe-volumes --volume-id {self.volume_id}"
        try:
            stdout, stderr, exitcode = self.cli.run(cmd)
            return json.loads(stdout)
        except CloudCliException as e:
            if "InvalidVolume.NotFound" in str(e):
                raise CloudStorageException(f"Volume {self.volume_id} does not exist")
            else:
                raise

    def wait_for_storage(self, event: AwsCli.StorageState):
        if event == self.cli.StorageState.ready:
            self.logger.info(f"Waiting until storage {self.volume_id} is ready")
        elif event == self.cli.StorageState.deleted:
            self.logger.info(f"Waiting for storage {self.volume_id} to be destroyed")

        cmd = f"ec2 wait {event} --volume-ids {self.volume_id}"
        _, _, _ = self.cli.run(cmd)

    def destroy(self):
        """Delete a single volume by id

        Args:
            volume_id ([type]): [description]

        aws ec2 wait volume-deleted --volume-id vol-0177709eb17c8d838 --region us-west-2
        """
        try:
            self.describe()
        except (AwsStorageException, CloudStorageException) as e:
            self.logger.warn(e)
        else:
            self.cli.delete_volume(self.volume_id)
            self.logger.info(f"Storage {self.volume_id} will be terminated soon")

    # TODO: An error occurred (IncorrectState) when calling the AttachVolume operation: Instance 'i-02e9791a4cc6dcaf4' is not 'running'.
    def attach_storage(self, vm: VirtualMachine):
        """
        requires self.create to be called first
        dev must be a device like /dev/sde
        """
        if self.vs.device == "":
            AwsStorageException("Could not attach storage without device")

        if vm.zone != self.vs.zone:
            AwsStorageException("Volume is instance must be in the same zone")

        cmd = f"ec2 attach-volume --volume-id {self.volume_id} --instance-id {vm.id} --device {self.vs.device}"
        self.logger.debug(f"Attaching volume {self.volume_id} to instance {vm.id}")
        _, _, _ = self.cli.run(cmd)
        self.wait_for_storage(self.cli.StorageState.in_use)

        # So called Nitro instance type which ignores device in API and uses NVMe type device even for EBS
        # Nitro instances: https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/instance-types.html#ec2-nitro-instances
        if self.is_nitro_type:
            self.vs.device = "/dev/nvme1n1"
            self.logger.debug(
                f"Instance {self.instance_type} uses nvme driver for EBS and device name has been renamed"
            )

    def detach_storage(self, vm: VirtualMachine):
        cmd = f"ec2 detach-volume --volume-id {self.volume_id}"
        self.logger.debug(f"detaching volume {self.volume_id}")
        _, _, _ = self.cli.run(cmd)
