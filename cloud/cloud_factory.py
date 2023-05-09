from cloud.abstract_cloud import AbstractCloud
from cloud.cloud_types import CloudTypeEnum
from cloud.exceptions import CloudException


class CloudFactory:
    __instance = None

    def __new__(cls):
        if not CloudFactory.__instance:
            CloudFactory.__instance = object.__new__(cls)
        return CloudFactory.__instance

    def create_cloud(
        self, cloud_type: CloudTypeEnum, cluster_name: str, **kwargs
    ) -> AbstractCloud:
        if cloud_type == CloudTypeEnum.AWS:
            from cloud.aws.aws_cloud import AwsCloud

            return AwsCloud(cluster_name, **kwargs)

        elif cloud_type == CloudTypeEnum.GCP:
            from cloud.gcp.gcp_cloud import GcpCloud

            return GcpCloud(cluster_name, **kwargs)
        
        elif cloud_type == CloudTypeEnum.AlloyDB:
            from cloud.gcp.gcp_alloydb_cloud import GcpAlloyDBCloud
            
            return GcpAlloyDBCloud(cluster_name, **kwargs)

        elif cloud_type == CloudTypeEnum.Aurora:
            from cloud.aws.aws_aurora_cloud import AwsAuroraCloud

            return AwsAuroraCloud(cluster_name, **kwargs)

        elif cloud_type == CloudTypeEnum.Rds:
            from cloud.aws.aws_rds_cloud import AwsRdsCloud

            return AwsRdsCloud(cluster_name, **kwargs)

        elif cloud_type == CloudTypeEnum.SkySql:
            from cloud.skysql.skysql import SkySQLCloud

            return SkySQLCloud(cluster_name, **kwargs)

        elif cloud_type == CloudTypeEnum.SkySql2:
            from cloud.skysql.skysql2 import SkySQLCloud2

            return SkySQLCloud2(cluster_name, **kwargs)

        elif cloud_type == CloudTypeEnum.Ephemeral:
            from cloud.ephemeral.ephemeral_cloud import EphemeralCloud

            return EphemeralCloud(cluster_name, **kwargs)

        elif cloud_type == CloudTypeEnum.Colo:
            from cloud.colo.sproutsys import Sproutsys

            return Sproutsys(cluster_name, **kwargs)

        else:
            raise CloudException(f"Cloud type not implemented: {cloud_type}")

    def create_cloud_from_str(
        self, cloud_type_str: str, cluster_name: str, **kwargs
    ) -> AbstractCloud:
        """Convenience method that internally calls `create_cloud(self, cloud_type: CloudTypeEnum ...)`"""
        cloud_type = CloudTypeEnum.from_string(cloud_type_str)
        return self.create_cloud(cloud_type, cluster_name, **kwargs)
