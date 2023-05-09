from dataclasses import dataclass
from typing import Optional

from backend.base_backend import BackendConfig
from compute import BackendTarget


@dataclass
class XpandConfig (BackendConfig):
    """Represents Xpand Config"""

    branch: str  # mainline1
    build: str  #  find the latest or could specify it 17441 as an example
    release: Optional[str]  # glassbutte has builds and releases
    license: str
    globals: dict
    prometheus_port: int
    enable_prometheus_exporter: bool
    clxnode_mem_pct: Optional[float]  # will override install_options
    space_allocation_pct: Optional[float]  # will override install_options
    hugetlb: Optional[bool]  #
    max_redo: Optional[int]  # Value in MB
    multi_page_alloc: Optional[int]  # Value in GB, default 1
    install_options: Optional[str]
    clxnode_additional_args: Optional[str]