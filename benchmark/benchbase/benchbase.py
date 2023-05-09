import logging

from benchmark.exceptions import BenchmarkException
from compute import Node, NodeException
from ..base_java_benchmark import BaseJavaBenchmark

DEFAULT_COMMAND_TIMEOUT = 300

BENCHBASE_GIT = "https://github.com/mariadb-corporation/benchbase"
BENCHBASE_JAVA_VERSION = "17"


class Benchbase(BaseJavaBenchmark):
    def __init__(self, node: Node, **kwargs):
        self.logger = logging.getLogger(__name__)
        self.node = node
        super().__init__(node=self.node, java_version=BENCHBASE_JAVA_VERSION)

    def install(self):
        try:
            super(Benchbase, self).install()
            self.logger.debug("Installing benchbase")
            cmd = f"""
            sudo pip3 install xmltodict
            cd $XBENCH_HOME
            git clone --depth 1 {BENCHBASE_GIT}
            cd benchbase
            ./mvnw -v
            """
            self.node.run(cmd)
            self.logger.debug("Benchbase successfully installed")
        except NodeException as e:
            raise BenchmarkException

    def clean(self):
        try:
            super(Benchbase, self).clean()
            self.logger.debug("Removing benchbase")
            cmd = """
            cd $XBENCH_HOME
            rm -rf benchbase
            """
            self.node.run(cmd)
            self.logger.debug("Benchbase successfully uninstalled")
        except NodeException as e:
            raise BenchmarkException
