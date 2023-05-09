from enum import Enum, unique

from cloud.exceptions import CloudException


@unique
class CloudTypeEnum(Enum):
    AWS = (1,)
    GCP = (2,)
    Ephemeral = (3,)
    Aurora = (4,)
    SkySql = (5,)
    Colo = (6,)
    SkySql2 = (7,)
    Rds = (8,)
    AlloyDB = (9,)

    @classmethod
    def from_string(cls, cloud_str: str):
        if cloud_str == "aws":
            return CloudTypeEnum.AWS
        elif cloud_str == "gcp":
            return CloudTypeEnum.GCP
        elif cloud_str == "aws_aurora":
            return CloudTypeEnum.Aurora
        elif cloud_str == "aws_rds":
            return CloudTypeEnum.Rds
        elif cloud_str == "skysql":
            return CloudTypeEnum.SkySql
        elif cloud_str == "skysql2":
            return CloudTypeEnum.SkySql2
        elif cloud_str == "colo":
            return CloudTypeEnum.Colo
        elif cloud_str == "gcp_alloydb":
            return CloudTypeEnum.AlloyDB
        else:
            raise CloudException(f"Unknown cloud type string: {cloud_str}")
