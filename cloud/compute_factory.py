
import dataclasses
from cloud.abstract_cli import AbstractCli
from cloud.abstract_compute import AbstractCompute
from cloud.exceptions import CloudException
from cloud.virtual_machine import VirtualMachine


class ComputeFactory:
    __instance = None

    def __new__(cls):
        if not ComputeFactory.__instance:
            ComputeFactory.__instance = object.__new__(cls)
        return ComputeFactory.__instance

    def create_compute_from_vm(self, cli: AbstractCli, vm: VirtualMachine):
        return self.create_compute(cli, **dataclasses.asdict(vm))

    def create_compute(self, cli: AbstractCli, **kwargs) -> AbstractCompute:
        from cloud.gcp import GcpCli, GcpCompute
        from cloud.aws import AwsCli, AwsEc2
        from cloud.gcp.gcp_alloydb_cli import GcpAlloyDBCli
        from cloud.gcp.gcp_alloydb_compute import GcpAlloyDBCompute
        if isinstance(cli, GcpAlloyDBCli):
            return GcpAlloyDBCompute(cli, **kwargs)
        if isinstance(cli, GcpCli):
            return GcpCompute(cli, **kwargs)
        if isinstance(cli, AwsCli):
            return AwsEc2(cli, **kwargs)
        else:
            raise CloudException(f"Compute type not implemented for CLI: {cli}")
