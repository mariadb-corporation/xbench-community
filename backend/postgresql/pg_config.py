from dataclasses import dataclass
from typing import Optional

from compute import BackendTarget

from ..base_backend import BackendConfig


@dataclass
class PGConfig(BackendConfig):
    version: str  # 10, 11, 12, 13, 14
    conf_file_template: str
    globals: Optional[dict]
    prometheus_port: int
    enable_prometheus_exporter: bool
