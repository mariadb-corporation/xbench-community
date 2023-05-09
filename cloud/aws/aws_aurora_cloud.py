# -*- coding: utf-8 -*-
# Copyright (C) 2022 dvolkov

from typing import Dict, List, Optional

from cloud.aws.aws_rds_compute import AwsRdsCompute
from cloud.cloud_types import CloudTypeEnum
from compute import Node

from ..abstract_cloud import AbstractCloud
from ..exceptions import CloudException
from .aws_aurora_cli import AwsAuroraCli
from .aws_aurora_compute import AwsAuroraCompute


class AwsAuroraCloud(AbstractCloud[AwsAuroraCli, AwsAuroraCompute]):
    def __init__(self, cluster_name: str, **kwargs):
        super(AwsAuroraCloud, self).__init__(cluster_name, **kwargs)

    def cloud_type(self) -> CloudTypeEnum:
        return CloudTypeEnum.Aurora

    def launch_instances(self, instances: List[Dict]) -> List[Optional[Node]]:
        """Launch instances
        Currently it handles only a single insance
        """
    
        self.compute = AwsAuroraCompute(self.cli, **instances[0])
        vm = self.compute.create()
        return [Node(vm)]

    def launch_instance(self, **instance_params) -> Optional[Node]:
        raise CloudException(f"Not implemented. Does not apply to {__name__}")

    def terminate_instance(self, instance: Node, terminate_storage: bool = False):
        raise CloudException(f"Not implemented. Does not apply to {__name__}")

    def terminate_instances(
        self, instances: List[Node], terminate_storage: bool = True
    ):
        self.compute = AwsAuroraCompute.from_vm(self.cli, instances[0].vm)
        self.compute.destroy()
