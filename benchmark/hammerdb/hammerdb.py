import logging

from benchmark.exceptions import BenchmarkException
from compute import Node, NodeException

DEFAULT_COMMAND_TIMEOUT = 300

HAMMERDB_GIT = "https://github.com/mariadb-corporation/HammerDB"


class Hammerdb:
    def __init__(self, node: Node, **kwargs):
        self.logger = logging.getLogger(__name__)
        self.node = node

    def configure(self):
        pass

    def install(self):
        try:
            self.logger.debug("Installing HammerDB")
            cmd = f"""
            cd $XBENCH_HOME
            git clone {HAMMERDB_GIT}
            cd HammerDB
            """
            self.node.run(cmd)
            self.logger.debug("HammerDB successfully installed")
        except NodeException as e:
            raise BenchmarkException

    def clean(self):
        try:
            self.logger.debug("Removing HammerDB")
            cmd = """
            cd $XBENCH_HOME
            rm -rf HammerDB
            """
            self.node.run(cmd)
            self.logger.debug("HammerDB successfully uninstalled")
        except NodeException as e:
            raise BenchmarkException
