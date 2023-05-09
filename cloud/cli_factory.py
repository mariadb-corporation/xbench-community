
from typing import Optional

from cloud.abstract_cli import AbstractCli
from cloud.cloud_types import CloudTypeEnum
from cloud.exceptions import CloudCliException


class CliFactory:
    __instance = None

    def __new__(cls):
        if not CliFactory.__instance:
            CliFactory.__instance = object.__new__(cls)
        return CliFactory.__instance

    def create_cli(self, cloud_type: CloudTypeEnum, cluster_name: str, **kwargs) -> Optional[AbstractCli]:
        if cloud_type == CloudTypeEnum.AWS:
            from cloud.aws.aws_cli import AwsCli
            return AwsCli(cluster_name, **kwargs)
        elif cloud_type == CloudTypeEnum.GCP:
            from cloud.gcp.gcp_cli import GcpCli
            return GcpCli(cluster_name, **kwargs)
        elif cloud_type == CloudTypeEnum.Ephemeral:
            return None
        elif cloud_type == CloudTypeEnum.Aurora:
            from cloud.aws.aws_aurora_cli import AwsAuroraCli
            return AwsAuroraCli(cluster_name, **kwargs)
        elif cloud_type == CloudTypeEnum.SkySql:
            return None
        elif cloud_type == CloudTypeEnum.SkySql2:
            return None
        elif cloud_type == CloudTypeEnum.Colo:
            from cloud.colo.sproutsys_cli import SproutsysCLI
            return SproutsysCLI(cluster_name, **kwargs)
        elif cloud_type == CloudTypeEnum.AlloyDB:
            from cloud.gcp.gcp_alloydb_cli import GcpAlloyDBCli
            return GcpAlloyDBCli(cluster_name, **kwargs)
        else:
            raise CloudCliException(f"Cloud type not implemented: {cloud_type}")

    def create_cli_from_str(self, cloud_type_str: str, cluster_name: str, **kwargs) -> Optional[AbstractCli]:
        """Convenience method that internally calls `create_cli(self, cloud_type: CloudTypeEnum ...)`
        """
        cloud_type = CloudTypeEnum.from_string(cloud_type_str)
        return self.create_cli(cloud_type, cluster_name, **kwargs)
