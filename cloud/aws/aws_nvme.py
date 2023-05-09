# https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/ssd-instance-store.html
# -*- coding: utf-8 -*-
# Copyright (C) 2022 dvolkov


import dataclasses
import logging
from typing import Dict

from cloud import VirtualMachine
from cloud.exceptions import CloudStorageException
from dacite import from_dict

from ..abstract_storage import AbstractStorage
from ..virtual_storage import VirtualStorage
from .aws_cli import AwsCli
from .exceptions import AwsStorageException


class AwsNvme(AbstractStorage[AwsCli, VirtualStorage]):
    def __init__(self, cli: AwsCli, vs: VirtualStorage, **kwargs):
        super(AwsNvme, self).__init__(cli, vs, **kwargs)

        self.region = cli.aws_region
        self.vs.name = f"{self.cluster_name}-nvme"
        self.vs.id = "nvme-001"

        #self.is_nitro_type = kwargs.get('is_nitro_type', True)
        #self.instance_type_info = kwargs.get('instance_type_info', {})

        self.instance_type = kwargs.get('instance_type')

        self.instance_type_info = self.cli.describe_instance_type(self.instance_type)
        self.is_nitro_type = True if self.instance_type_info.get("nvme_support") == "required" else False

    def create(self) -> VirtualStorage:
        """Check that NVMe exists?

        Returns:
            VirtualStorage: _description_
        """
        # Nitro already has one device for the root
        start_from = 1 if self.is_nitro_type else 0

        if self.instance_type_info.get("local_nvme") is not True:
            self.logger.error(
                f"Instance {self.instance_type} does not have local NVMe"
            )
        else:
            # Count number of local ssd from Aws instance_type_info
            local_nvme_disks = self.instance_type_info.get(
                "local_nvme_disks", None
            )
            if local_nvme_disks is not None:
                self.vs.num_ephemeral = local_nvme_disks[0].get("Count")
            else:
                self.vs.num_ephemeral = 0

        num_local_volumes = self.vs.num_ephemeral
        if num_local_volumes == 1:
            self.vs.device = f"/dev/nvme{start_from}n1"
        if num_local_volumes > 1:
            all_nvme = [f"/dev/nvme{i}n1" for i in range(start_from, num_local_volumes + start_from)]
            self.vs.device = ",".join(all_nvme)

        return self.vs

    def describe(self) -> Dict:
        raise CloudStorageException()

    def destroy(self):
        pass

    def attach_storage(self, vm: VirtualMachine):
        pass

    def detach_storage(self, vm: VirtualMachine):
        pass
