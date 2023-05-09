from cloud import VirtualMachine
from compute import Node
from dacite import from_dict

from ..abstract_cloud import AbstractCli


class SproutsysCLI(AbstractCli):
    def __init__(self, cluster_name, **kwargs):
        super(SproutsysCLI, self).__init__(cluster_name, **kwargs)

    def deploy_host(self, host: str, instance_params: dict) -> Node:
        new_vm: VirtualMachine = from_dict(
            data_class=VirtualMachine, data=instance_params
        )
        # might have to set `new_vm.provisioned = False` for the correct deprovisioning behavior
        new_vm.id = f"colo-{instance_params.get('name')}-{self.cluster_name}-{host}"
        new_vm.zone = "not a real zone"
        if new_vm.storage:
            new_vm.storage.zone = "not a real zone"
        new_vm.network.public_ip = host
        n: Node = Node(new_vm)
        n.vm.network.public_ip = n.run(f"host {host} | awk '{{print $NF}}'")
        if instance_params.get("role") == "backend":
            n.vm.network.private_ip = n.run(f"host {host}-10g | awk '{{print $NF}}'")
        else:
            n.vm.network.private_ip = n.run(f"host {host} | awk '{{print $NF}}'")
        return n

    def check_cli_version(self):
        pass

    def describe_instances_by_tag(self) -> list[dict]:
        return [{}]

    def terminate_instances(self, instances: list[dict]):
        pass

    def wait_for_instances(self, instances: list[dict], instance_status: str):
        pass

    def describe_volumes_by_tag(self) -> list[dict]:
        pass

    def delete_volumes(self, volumes: list[dict]):
        pass
