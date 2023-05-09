# -*- coding: utf-8 -*-
# Copyright (C) 2021 dvolkov

import inspect
from dataclasses import dataclass
from typing import Optional

from .virtual_storage import VirtualStorage

# It could be next possible scenarios

# Colo, Sky/Cockroach a.k.a private_cloud
# workload driver uses public ip
# nodes uses private ip
# external access (vqc) uses public

# AWS and I3  a.k.a public_cloud
# nodes uses private ip
# driver uses private ip
# external access (vqc) uses public

# secure_cloud?
# nodes and driver uses private ips only
# external access (vqc) uses public


@dataclass
class VirtualNetwork:
    """Define virtual network in a cloud"""

    cloud_type: str = "public_cloud"  # could be public_cloud or private_cloud
    private_ip: str = "127.0.0.1"
    public_ip: str = "127.0.0.1"
    disable_network_security: bool = True # Disable iptables and firewall

    def get_client_iface(self):
        return self.public_ip if self.cloud_type == "private_cloud" else self.private_ip

    def get_public_iface(self):
        return self.public_ip

    def get_private_iface(self):
        return self.private_ip
