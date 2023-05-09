# -*- coding: utf-8 -*-
# Copyright (C) 2021 dvolkov

from dataclasses import dataclass, field
from typing import List, Optional

from cloud.arch_types import X86_64

from .virtual_network import VirtualNetwork
from .virtual_storage import VirtualStorage


@dataclass
class VirtualMachine:
    """Define virtual machine in a cloud"""

    env: str  # environment
    cloud: str  #  label in cloud.yaml
    cluster_name: str
    name: str  # = "vm"  # human readable name e.x. driver1, proxy1, database2
    role: str  # = ""  driver, backend
    klass: str  # backend.Xpand
    klass_config_label: str  # label in specific class configuration
    instance_type: str  # = ""
    zone: str  # = ""
    os_type: str  # = ""
    managed: bool  # If I ever need to ssh to this node
    provisioned: bool  # If I need to call cloud provisioning for this node
    arch: str = X86_64  # amd64, arm64
    key_file: str = ""  # For none managed instances
    pub_file: str = ""
    # storage is kept for backwards-compatiblity
    storage: Optional[VirtualStorage] = None
    # storage_list supercedes storage
    storage_list: List[VirtualStorage] = field(default_factory=list)
    network: Optional[VirtualNetwork] = None
    placement_group: Optional[str] = None
    id: Optional[str] = None  # Cloud Id which uniquely identify the machine (for CLI)
    ssh_user: str = "root"

    def labels(self):
        return {
            "cloud": self.cloud,
            "cluster_name": self.cluster_name,
            "zone": self.zone,
            "machine_type": self.instance_type,
            "role": self.role,
            "name": self.name,
        }

    def get_all_storage(self) -> List[VirtualStorage]:
        return self.storage_list + ([self.storage] if self.storage is not None else [])
