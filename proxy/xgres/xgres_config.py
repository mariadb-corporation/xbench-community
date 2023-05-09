from dataclasses import dataclass

from compute import BackendTarget


@dataclass
class XgresConfig:
    """Represents Xgres Config"""

    db: BackendTarget
    xgres_git_token: str
    xgres_query_path: str  # "FDW" or anything else for dblink
    build_tag: str = "v0.2"  # "HEAD"
    pg_build_tag: str = "mariadb"
