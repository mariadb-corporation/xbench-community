# Consider this before modifying the code below:
# https://stackoverflow.com/questions/9575409/calling-parent-class-init-with-multiple-inheritance-whats-the-right-way

import logging
import os
from dataclasses import dataclass
from typing import List, Mapping, Optional, Tuple, Type

from dacite import from_dict

from compute import Node
from compute.backend_dialect import BackendDialect
from compute.backend_product import BackendProduct
from compute.backend_target import BackendTarget
from compute.multi_node import MultiNode
from compute.yum import Yum
from lib import XbenchConfig

RUN_COMMAND_TIMEOUT = 600  # single command should't take longer


@dataclass
class BackendConfig:
    """Represents Backend Config for both managed and unmanaged cases"""

    db: BackendTarget
    data_dir: Optional[str]  # unmanaged backends don't need it

    def update(self, updates: Mapping):
        """
        Update nested properties of the `db` attribute and `data_dir`.

        Usage:
        config.update({ "db": { "host": "new_host", "user": "new_user" }, "data_dir": "/path/to/new/data_dir" })
        """
        for key, value in updates.items():
            if key == "db":
                for db_key, db_value in value.items():
                    setattr(self.db, db_key, db_value)
            else:
                setattr(self, key, value)


def mdadm_command(node: Node) -> Tuple[Optional[str], Optional[str]]:
    logger = logging.getLogger(__name__)
    storage_list = node.vm.get_all_storage()
    device = None
    for storage in storage_list:
        device = storage.device
        if storage.type == 'ephemeral':
            logger.info("Backend is going to use internal NVMe drives")
        # in case of local nmve device is a string with possibly multiple devices
        if storage.num_ephemeral > 0:
            local_volumes = device.split(",")
            num_local_volumes = len(local_volumes)

            if num_local_volumes > 1:
                device = "/dev/md0"
                cmd = (
                    f"mdadm --create {device} -l0"
                    f" -n{num_local_volumes} {' '.join(local_volumes)}"
                )
                return (cmd, device)  # Multiple NVMe
            else:
                return (None, device)  # Single NVMe

    return (None, device)


def mkdir_command(
    directory, device, mount_to_parent: bool = False, chmod: bool = False
) -> str:
    mountpoint = directory
    fs_type: str = "ext4"
    mount_options: str = ",".join(["discard", "defaults", "nofail"])
    if mount_to_parent:
        mountpoint = os.path.dirname(os.path.normpath(directory))

    chmod_cmd = (
        "chmod -R 777 {directory}" if chmod else "echo"
    )  # dummy echo instead of chmod

    cmd = f"""
        mkdir -p {directory}
        ! mountpoint -q {mountpoint} || umount -f {mountpoint}
        mkfs.{fs_type} -F -j {device}
        mount {device} {mountpoint}
        mkdir -p {directory}
        echo "UUID=$(sudo blkid -s UUID -o value {device}) {mountpoint} {fs_type} {mount_options} 0 2" | sudo tee -a /etc/fstab
        {chmod_cmd}
        tune2fs -m1 {device}
        """
    return cmd


class BaseBackend:
    clustered = False
    dialect = BackendDialect.mysql
    product = BackendProduct.mysql

    def __init__(
        self,
        backend_config_yaml_file: str,
        backend_config_label: str,
        backend_config_klass: Type[BackendConfig],
        **kwargs,
    ):
        extra_config_params = {}
        self.logger = logging.getLogger(__name__)
        self.xbench_config = XbenchConfig().xbench_config
        override_config_klass_label = kwargs.get("override_config_klass_label", None)
        key_name = (
            override_config_klass_label
            if override_config_klass_label
            else backend_config_label
        )
        self.config = from_dict(
            backend_config_klass,
            data=XbenchConfig().get_key_from_yaml(
                yaml_file_name=backend_config_yaml_file,
                key_name=key_name,
                use_defaults=True,
            ),
        )
        self.config.db.update(kwargs.get("bt", {}))
        # Let's check if we've got extra config parameters from command line
        if kwargs is not None:
            try:
                extra_config_params = kwargs["backend"][
                    "config"
                ]  # This is by agreement - you can pass --backend.config.parameter=value to xbench.sh
            except KeyError:
                pass

        if extra_config_params is not None:
            self.config.update(extra_config_params)


class MultiUnManagedBackend(MultiNode, BaseBackend):
    """Generic class for single node unmanaged backends"""

    def __init__(
        self,
        nodes: List[Node],
        backend_config_yaml_file: str,
        backend_config_klass: Type[BackendConfig],
        **kwargs,
    ):

        MultiNode.__init__(self, nodes)
        self.config_label = self.head_node.vm.klass_config_label
        self.logger.debug(f"Using {self.config_label} for xpand installation")

        BaseBackend.__init__(
            self,
            backend_config_yaml_file,
            self.config_label,
            backend_config_klass,
            **kwargs,
        )
        self.config.db.host = ",".join(self._all_private_ips())
        self.config.db.dialect = self.dialect
        self.config.db.product = self.product


class SingleUnManagedBackend(BaseBackend):
    """Generic class for single node unmanaged backends"""

    def __init__(
        self,
        node: Node,
        backend_config_yaml_file: str,
        backend_config_klass: Type[BackendConfig],
        **kwargs,
    ):

        self.node = node
        super(SingleUnManagedBackend, self).__init__(
            backend_config_yaml_file,
            self.node.vm.klass_config_label,
            backend_config_klass,
            **kwargs,
        )
        self.config.db.host = node.vm.network.get_public_iface()
        self.config.db.dialect = self.dialect
        self.config.db.product = self.product


class SingleManagedBackend(SingleUnManagedBackend):
    """Generic class for single node managed backends"""

    def __init__(
        self,
        node: Node,
        backend_config_yaml_file: str,
        backend_config_klass: Type[BackendConfig],
        **kwargs,
    ):

        super(SingleManagedBackend, self).__init__(
            node,
            backend_config_yaml_file,
            backend_config_klass,
            **kwargs,
        )
        self.yum = Yum(os_type=self.node.vm.os_type)
        self.mount_storage_to_parent = kwargs.get("mount_storage_to_parent", False)

    def run(self, cmd, user: str = None):
        """Run command on backend

        Args:
            cmd (str): command to run, could be multiline
            user (str): OS user to run command with
        """
        self.node.run(cmd, timeout=RUN_COMMAND_TIMEOUT, sudo=True, user=user)

    def configure(self):
        self.logger.info(f"Running {self.product} configure")
        directory = self.config.data_dir
        cmd, device = mdadm_command(self.node)
        if cmd is not None:
            self.run(cmd)
        if device is not None:
            self.run(mkdir_command(directory, device, self.mount_storage_to_parent))


class MultiManagedBackend(MultiUnManagedBackend):
    """Generic class for multimode node managed backends"""

    def __init__(
        self,
        nodes: List[Node],
        backend_config_yaml_file: str,
        backend_config_klass: Type[BackendConfig],
        **kwargs,
    ):

        MultiUnManagedBackend.__init__(
            self, nodes, backend_config_yaml_file, backend_config_klass, **kwargs
        )
        self.mount_storage_to_parent = kwargs.get("mount_storage_to_parent", False)

    def configure(self):
        self.logger.info(f"Running {self.product} configure")

        directory = self.config.data_dir

        cmd, device = mdadm_command(self.head_node)
        if cmd is not None:
            self.run_on_all_nodes(cmd)

        if device is not None:
            self.run_on_all_nodes(
                mkdir_command(directory, device, self.mount_storage_to_parent)
            )
