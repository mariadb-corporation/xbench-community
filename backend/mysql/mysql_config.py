from dataclasses import dataclass
from typing import Optional


from ..base_backend import BackendConfig


@dataclass
class MySqlDBConfig(BackendConfig):
    """Represents Xpand Config"""

    release: str
    cnf_template: str  # cnf template file name
    globals: Optional[dict]
    prometheus_port: int
    enable_prometheus_exporter: bool
    binlog: bool = False
    enterprise_download_token: str = ""
