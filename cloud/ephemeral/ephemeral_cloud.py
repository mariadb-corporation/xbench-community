# -*- coding: utf-8 -*-
# Copyright (C) 2021 dvolkov

import logging
import os
from typing import Dict, List, Optional

from dacite import from_dict

from cloud.abstract_cloud import AbstractCloud
from cloud.cloud_types import CloudTypeEnum
from cloud.exceptions import CloudException
from cloud.virtual_machine import VirtualMachine
from compute import Node


class EphemeralCloud(AbstractCloud[None, None]):
    """Cloud class to managed externally managed backends"""

    def __init__(self, cluster_name: str, **kwargs):
        super(EphemeralCloud, self).__init__(cluster_name, **kwargs)

        self.default_config = {
            "cloud": "Ephemeral",
            "cluster_name": self.cluster_name,
            "id": "e-12345678",
            "ssh_user": "nobody",
            "key_file": f"{os.path.expanduser('~')}/.xbench/pem/xbench.pem",
            "instance_type": "ec2",
            "zone": "wild_west_2",
            "os_type": "CentOS7",  # Have to be real, Node verifies this
            "managed": False,
            "network": {
                "cloud_type": "public_cloud",
                "private_ip": "0.0.0.0",
                "public_ip": kwargs.get("public_ip"),
            },
        }

    def cloud_type(self) -> CloudTypeEnum:
        return CloudTypeEnum.Ephemeral

    def is_running(self) -> bool:
        raise CloudException("Not implemented")

    def launch_instances(self, instances: List[Dict]) -> List[Optional[Node]]:
        self.logger.debug(instances)
        all_nodes: List[Optional[Node]] = [
            Node(from_dict(data_class=VirtualMachine, data=self.default_config | param))
            for param in instances
        ]
        return all_nodes

    def launch_instance(self, **instance_params) -> Optional[Node]:
        raise CloudException(f"Not implemented. Does not apply to {__name__}")

    def terminate_instances(
        self, instances: List[Node], terminate_storage: bool = True
    ):
        raise CloudException("Not implemented")

    def terminate_instance(self, instance: Node, terminate_storage: bool = False):
        raise CloudException(f"Not implemented. Does not apply to {__name__}")
