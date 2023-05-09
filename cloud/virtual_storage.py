# -*- coding: utf-8 -*-
# Copyright (C) 2021 dvolkov

from dataclasses import dataclass
from typing import Optional


@dataclass
class VirtualStorage:
    """Define virtual machine in a cloud"""

    size: int = 0  # 500 Gb
    iops: int = 0  # = 1000
    type: Optional[str] = None
    device: str = "/dev/xvdb"
    zone: str = "us_west_2a"
    name: str = "volume"
    id: str = ""  #  vol-0f209c91b7e82ce9c for AWS
    num_ephemeral: int = 0  # Number of local disks to use

    @property
    def is_shared(self) -> bool:
        return False
