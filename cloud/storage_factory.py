
from typing import Optional, cast

from cloud.abstract_cli import AbstractCli
from cloud.abstract_storage import AbstractStorage
from cloud.exceptions import CloudException
from cloud.virtual_machine import VirtualMachine
from cloud.virtual_storage import VirtualStorage


class StorageFactory:
    __instance = None

    def __new__(cls):
        if not StorageFactory.__instance:
            StorageFactory.__instance = object.__new__(cls)
        return StorageFactory.__instance

    def create_storage(self, cli: AbstractCli, virtual_storage: VirtualStorage, vm: Optional[VirtualMachine] = None, **kwargs) -> AbstractStorage:
        from cloud.aws import AwsCli
        from cloud.colo import SproutsysCLI
        from cloud.gcp import GcpCli, GcpNasStorage, GcpStorage

        if isinstance(cli, GcpCli):
            if virtual_storage.type == "filestore":
                return GcpNasStorage(cli=cli, vs=virtual_storage)
            else:
                return GcpStorage(cli=cli, vs=virtual_storage, vm_name=vm.name if vm is not None else "")
        elif isinstance(cli, AwsCli):
            from cloud.aws import AwsEbs, AwsNvme, AwsS3
            if virtual_storage.type == "ephemeral":
                return AwsNvme(cli=cli, vs=virtual_storage, **kwargs)
            if virtual_storage.type in ["io1", "io2", "gp2", "gp3", "st1", "sc1", "standard"]: # AWS-specific types are supported for backwards-compatibility
                return AwsEbs(cli=cli, vs=virtual_storage, **kwargs)
            if virtual_storage.type == "s3":
                return AwsS3(cli=cli, vs=virtual_storage, **kwargs)
        elif isinstance(cli, SproutsysCLI):
            from cloud.colo import ColoNvme
            if virtual_storage.type == "ephemeral":
                return ColoNvme(cli=cli, vs=virtual_storage, **kwargs)
        raise CloudException(f"Storage type not implemented: {virtual_storage.type}")
