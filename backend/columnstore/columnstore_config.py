# -*- coding: utf-8 -*-
# Copyright (C) 2021 detravi

from dataclasses import dataclass
from typing import Optional

from compute import BackendTarget
from backend.base_backend import BackendConfig

@dataclass
class ColumnStoreConfig(BackendConfig):
    """Represents Columnstore Config"""

    branch: Optional[str] # mainline1
    build: str  #  find the latest or could specify it 17441 as an example
    server_version: str
    release: Optional[str]  # glassbutte has builds and releases
    mcs_baseurl: Optional[str]
    cmapi_baseurl: Optional[str]
    packages_path : Optional[str]
    db: BackendTarget
    globals: dict
    prometheus_port: int
    enable_prometheus_exporter: bool
