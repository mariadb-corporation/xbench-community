# https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/ssd-instance-store.html
# -*- coding: utf-8 -*-
# Copyright (C) 2022 dvolkov


from typing import Dict

from cloud import VirtualMachine
from cloud.exceptions import CloudStorageException

from ..abstract_storage import AbstractStorage
from ..virtual_storage import VirtualStorage
from .sproutsys_cli import SproutsysCLI


class ColoNvme(AbstractStorage[SproutsysCLI, VirtualStorage]):
    def __init__(self, cli: SproutsysCLI, vs: VirtualStorage, **kwargs):
        super(ColoNvme, self).__init__(cli, vs, **kwargs)

        # self.region = cli.aws_region
        self.vs.name = f"{self.cluster_name}-nvme"
        self.vs.id = "nvme-001"
        self.vs.num_ephemeral = 1

    def create(self) -> VirtualStorage:
        """Check that NVMe exists?

        Returns:
            VirtualStorage: _description_
        """
        self.vs.device = f"/dev/nvme1n1" # This is what all Colo machines have
        print ("I AM COLO NVMe")
        return self.vs

    def describe(self) -> Dict:
        raise CloudStorageException()

    def destroy(self):
        pass

    def attach_storage(self, vm: VirtualMachine):
        pass

    def detach_storage(self, vm: VirtualMachine):
        pass
