from dataclasses import dataclass
from typing import Optional

from backend.base_backend import BackendConfig
from compute import BackendTarget


@dataclass
class RdsMySqlConfig(BackendConfig):
    """Represents Xpand Config"""

    engine_version: str
    globals: dict
    db_parameter_group_name: str
    engine: str = "mariadb"
