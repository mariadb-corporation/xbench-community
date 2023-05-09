# -*- coding: utf-8 -*-
# Copyright (C) 2021 dvolkov

import logging

from compute import Node, NodeException
from compute.yum import Yum

from ..exceptions import BenchmarkException

DEFAULT_COMMAND_TIMEOUT = 300


class Locust:
    def __init__(self, node: Node, **kwargs):
        self.node = node
        self.logger = logging.getLogger(__name__)
        self.yum = Yum(os_type=self.node.vm.os_type)

    # ToDo: compile sysbench for different platforms and set aliases
    def configure(self):
        # git should come from the base_driver class
        # unfortunately python3 is 3.6 so I have to install python39
        pm_i = self.yum.install_pkg_cmd()
        cmd = f"""
        {pm_i} python39
        """
        stdout = self.node.run(cmd, timeout=DEFAULT_COMMAND_TIMEOUT, sudo=True)
        self.logger.debug(stdout)

    def install(self):
        try:
            self.logger.debug("Cloning Xpand-Locust...")
            cmd = """cd $XBENCH_HOME
            git clone https://github.com/mariadb-corporation/xpand-locust.git
            pip3.9 install -r $XBENCH_HOME/xpand-locust/requirements.txt

            [[ ${XPAND_LOCUST_HOME} ]] || {
            echo 'export XPAND_LOCUST_HOME=$XBENCH_HOME/xpand-locust' >> ~/.bashrc
            echo 'export PATH=$XPAND_LOCUST_HOME/bin:$PATH' >> ~/.bashrc
            echo 'export PYTHONPATH=$XPAND_LOCUST_HOME' >> ~/.bashrc
            }
            """
            stdout = self.node.run(cmd, timeout=DEFAULT_COMMAND_TIMEOUT)
            self.logger.debug(stdout)
            self.logger.debug("Xpand-locust successfully installed")
        except NodeException as e:
            raise BenchmarkException

    def clean(self):
        output = self.node.run(
            "pkill -9 python3.9 || true", timeout=DEFAULT_COMMAND_TIMEOUT
        )
        self.logger.debug(output)
        cmd = """
        sed -i '/^export XPAND_LOCUST_HOME/d' ~/.bashrc
        cd $XBENCH_HOME
        rm -rf xpand-locust
        """
        stdout = self.node.run(cmd, timeout=DEFAULT_COMMAND_TIMEOUT)
        self.logger.debug("Locust successfully uninstalled")
