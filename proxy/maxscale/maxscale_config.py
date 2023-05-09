from dataclasses import dataclass
from typing import Optional

from compute import BackendTarget


@dataclass
class MaxscaleConfig:
    """Represents Xpand Config"""

    release: str
    db: BackendTarget
    prometheus_port: int
    enable_prometheus_exporter: bool
    enterprise_download_token: str = ""
    cnf_config_template: str = "maxscale_xpand.cnf"
