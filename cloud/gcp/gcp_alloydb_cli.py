from typing import Dict

from . import GcpCli


class GcpAlloyDBCli(GcpCli):
    def get_base_command(self) -> str:
        cmd = super().get_base_command()
        return f"{cmd} alloydb "
    
    def check_cli_version(self):
        # disabled due to the "beta alloydb" in get_base_command()
        pass

    def describe_instance(self):
        pass

    def describe_instances_by_tag(self):
        return []

    def terminate_instances(self, instances: list[Dict]):
        """Terminated instances"""
        pass

    def wait_for_instances(self, instances: list[Dict], instance_status: str):
        """Wait for status"""
        pass

    def describe_volumes_by_tag(self) -> list[Dict]:
        """List of attached volumes per cluster"""
        pass

    def delete_volumes(self, volumes: list[Dict]):
        """Delete attached volumes"""
        pass
