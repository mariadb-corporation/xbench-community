# -*- coding: utf-8 -*-
# Copyright (C) 2021 dvolkov

import asyncio
import concurrent.futures
import logging
from multiprocessing import cpu_count
from typing import Dict, List, Optional

from cloud.aws.aws_nvme import AwsNvme
from cloud.cloud_types import CloudTypeEnum
from cloud.virtual_machine import VirtualMachine
from cloud.virtual_storage import VirtualStorage
from compute import Node
from metrics import MetricsServer

from ..abstract_cloud import AbstractCloud
from .aws_cli import AwsCli
from .aws_ebs import AwsEbs
from .aws_ec2 import AwsEc2
from .aws_s3 import AwsS3
from .exceptions import AwsCloudException, AwsEc2Exception, AwsStorageException

AWS_CLI_VERSION_REQUIRED = "2."


# TODO nuke cluster - delete everything based on tag - check aws.release
# Name=tag:Name,Values=${CLUSTER}*
# Do not create the cluster if it is already running


class AwsCloud(AbstractCloud[AwsCli, AwsEc2]):
    def cloud_type(self) -> CloudTypeEnum:
        return CloudTypeEnum.AWS

    def launch_storage(
        self,
        attach_to_vm: Optional[VirtualMachine],
        storage_params: VirtualStorage,
        **kwargs
    ) -> Optional[VirtualStorage]:
        if attach_to_vm is not None:
            # We need storage and instance to be in the same zone
            storage_params.zone = attach_to_vm.zone
        virtual_storage = super().launch_storage(attach_to_vm, storage_params, **kwargs)
        return virtual_storage

    def launch_instance(self, **instance_params) -> Optional[Node]:
        """Launch a single instance

        Returns:
            Node: Node object (which can do ssh for example!)
        """
        try:
            self.instance_type = instance_params.get("instance_type")
            self.instance_type_info = self.cli.describe_instance_type(
                self.instance_type
            )
            self.is_nitro_type = (
                True
                if self.instance_type_info.get("nvme_support") == "required"
                else False
            )

            return super().launch_instance(**instance_params)
        except AwsCloudException as e:
            self.logger.error(e)
            return None
