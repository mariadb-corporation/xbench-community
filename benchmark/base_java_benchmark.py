import logging
from typing import Optional

from benchmark.exceptions import BenchmarkException
from compute import Node, NodeException
from compute.yum import Yum

DEFAULT_JAVA_VERSION = "17"


class BaseJavaBenchmark:
    """Base class for all sort of java based benchmarks"""

    def __init__(self, node: Node, java_version: Optional[str]):

        self.logger = logging.getLogger(__name__)
        self.node = node
        self.java_version = java_version or DEFAULT_JAVA_VERSION
        self.yum = Yum(os_type=self.node.vm.os_type)

    def configure(self):
        pass

    def install(self):
        try:
            self.logger.debug(f"Installing java version {self.java_version}")
            # TODO: dnf update -y has been removed
            # TODO: the rpm suffix will fail on non-redhat distros
            pm_local_install = self.yum.install_local_pkg_cmd()
            cmd = f"""
            wget https://download.oracle.com/java/17/latest/jdk-{self.java_version}_linux-x64_bin.rpm
            {pm_local_install} jdk-{self.java_version}_linux-x64_bin.rpm
            """
            self.node.run(cmd, sudo=True)
            self.logger.debug("Java successfully installed")
        except NodeException as e:
            raise BenchmarkException(e)

    def clean(self):
        try:
            pm_remove = self.yum.remove_pkg_cmd()
            cmd = f"""
            {pm_remove} jdk-{self.java_version}_linux-x64_bin.rpm
            rm -rf jdk-{self.java_version}_linux-x64_bin.rpm
            """
            self.node.run(cmd, sudo=True)
        except NodeException as e:
            raise BenchmarkException(e)
