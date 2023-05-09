# -*- coding: utf-8 -*-
# Copyright (C) 2021 dvolkov

import logging

from compute import Node, NodeException

from ..exceptions import BenchmarkException

DEFAULT_COMMAND_TIMEOUT = 300


class Sysbench:
    def __init__(self, node: Node, **kwargs):
        self.node = node
        self.logger = logging.getLogger(__name__)

    # ToDo: compile sysbench for different database engines and set aliases
    def configure(self):
        pass

    def install(self):
        try:
            """Cloning sysbench from our own public repo"""
            self.logger.debug("Cloning Sysbench...")
            cmd = """
            cd $XBENCH_HOME
            git clone https://github.com/mariadb-corporation/sysbench-bin
            sysbench-bin/bin/sysbench --version
            if ! command -v sysbench 1>/dev/null 2>&1; then
            echo 'export SYSBENCH_HOME=$XBENCH_HOME/sysbench-bin' >> ~/.bashrc
            echo 'export PATH=$SYSBENCH_HOME/bin:$PATH' >> ~/.bashrc
            echo 'export LD_LIBRARY_PATH=/usr/lib64:$LD_LIBRARY_PATH' >> ~/.bashrc
            echo 'export LUA_PATH=$SYSBENCH_HOME/lua/?.lua' >> ~/.bashrc
            fi
            """
            stdout = self.node.run(cmd, timeout=DEFAULT_COMMAND_TIMEOUT)
            self.logger.debug(stdout)
            self.logger.debug("Sysbench successfully installed")
        except NodeException as e:
            raise BenchmarkException

    def _parse_output(self):
        # https://github.com/GoogleCloudPlatform/PerfKitBenchmarker/commit/5803fcc3170008ac1464eee358dd52b1c1254a80?branch=5803fcc3170008ac1464eee358dd52b1c1254a80&diff=unified#diff-723a300e03dd756ca865d26bf09d0f1ebff4e85080ad94c55e6958ff63ec891e
        pass

    def run(self, cluster_name, **kwargs):
        # /root/CloudBench/clustrixbench/bin/sysbench.run.sh --cluster dv-aws-xpand-c5d.2xlarge-3_nodes.maxscale --skipcheck --benchmark sysbench --workload 9010 --driver sysbench --schema sysbench --dbscale 10 --totalstreams 8 --tables 10
        # COMMAND = sysbench oltp_read_write --point-selects=9 --range-selects=false --index-updates=0 --non-index-updates=1 --delete-inserts=0 --rand-type=uniform --report-interval=10 --warmup-time=60 --tables=10 --table-size=1000000 --time=300  --histogram --mysql-db=sysbench --db-driver=mysql --mysql-host=172.30.1.61,172.30.1.16 --mysql-user=cbench --mysql-password=Ma49DB4F#+Pa13w0rd --mysql-port=3306 --mysql-ssl=on --threads=4 --rand-seed=1234567 run
        # SYSBENCH_OPTIONS   = --histogram ??

        # COMMAND = sysbench oltp_read_write --point-selects=9 --range-selects=false --index-updates=0 --non-index-updates=1 --delete-inserts=0 --rand-type=uniform --report-interval=10 --warmup-time=60 --tables=10 --table-size=1000000 --time=300  --histogram --mysql-db=sysbench --db-driver=mysql --mysql-host=172.31.45.93,172.31.35.194 --mysql-user=cbench --mysql-password=Ma49DB4F#+Pa13w0rd --mysql-port=3306 --mysql-ssl=on --threads=4 --rand-seed=1234567 run
        pass

    def clean(self):
        output = self.node.run(
            "pkill -9 sysbench || true", timeout=DEFAULT_COMMAND_TIMEOUT
        )
        print(output)
        cmd = """
        sed -i '/^export LUA_PATH/d' ~/.bashrc
        sed -i '/^export LD_LIBRARY/d' ~/.bashrc
        sed -i '/^export PATH/d' ~/.bashrc
        sed -i '/^export SYSBENCH_HOME/d' ~/.bashrc
        cd $XBENCH_HOME
        rm -rf sysbench-bin
        """
        stdout = self.node.run(cmd, timeout=DEFAULT_COMMAND_TIMEOUT)
        self.logger.debug("Sysbench successfully uninstalled")
