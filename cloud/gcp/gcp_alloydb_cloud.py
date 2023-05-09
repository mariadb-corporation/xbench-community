from copy import deepcopy
from typing import Dict, List, Optional, Sequence

from cloud.aws.aws_ec2 import AwsEc2
from cloud.cloud_types import CloudTypeEnum
from compute import Node

from ..abstract_cloud import AbstractCloud
from ..exceptions import CloudException
from .gcp_alloydb_cli import GcpAlloyDBCli
from .gcp_alloydb_compute import GcpAlloyDBCompute


class GcpAlloyDBCloud(AbstractCloud[GcpAlloyDBCli, GcpAlloyDBCompute]):
    def __init__(self, cluster_name: str, **kwargs):
        super(GcpAlloyDBCloud, self).__init__(cluster_name, **kwargs)

    def cloud_type(self) -> CloudTypeEnum:
        return CloudTypeEnum.AlloyDB

    def launch_instances(self, instances: List[Dict]) -> List[Optional[Node]]:
        """Launch instances
        Currently it handles only a single instance
        """
        node_count = len(instances)
        alloydb_compute = GcpAlloyDBCompute(self.cli, **instances[0])
        vm = alloydb_compute.create(node_count=node_count)

        # We always return only one instance - primary.
        # In case of read-only I just have to return list.
        returned_instances: List[Node] = []
        if node_count > 1:
            for i in instances:
                read_only_vm = deepcopy(vm)
                read_only_vm.name = i.get(
                    "name"
                )  # I have to change name as this is a key in cluster file
                returned_instances.append(Node(read_only_vm))
        else:
            returned_instances = [Node(vm)]
        return returned_instances

    def launch_instance(self, **instance_params) -> Optional[Node]:
        raise CloudException(f"Not implemented. Does not apply to {__name__}")

    def terminate_instance(self, instance: Node, terminate_storage: bool = False):
        raise CloudException(f"Not implemented. Does not apply to {__name__}")

    def terminate_instances(
        self, instances: List[Node], terminate_storage: bool = True
    ):
        alloydb_compute = GcpAlloyDBCompute.from_vm(self.cli, instances[0].vm)
        alloydb_compute.destroy()
