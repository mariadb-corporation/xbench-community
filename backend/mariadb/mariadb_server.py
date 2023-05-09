# -*- coding: utf-8 -*-
# Copyright (C) 2022 dvolkov


from compute import Node

from .mariadb import MariaDB

# Community check out --source mariadb.org --release 10.8
# http://storage02.colo.sproutsys.com/pub/qa/performance/log/XL/vm2-ES-16/220414.185236.aws.scaleout/220414.185421609.build.cluster/220414.185421615.build.cluster.log


class MariaDBServer(MariaDB):
    """Community MariaDB Server"""

    clustered = False

    def __init__(
        self,
        node: Node,
        **kwargs,
    ):
        super(MariaDBServer, self).__init__(node, **kwargs)

    def download(self):
        """
        https://mariadb.com/resources/blog/how-to-install-mariadb-on-rhel8-centos8/
        https://mariadb.com/docs/reference/mariadb_repo_setup/
        """
        cmd = f"""
        {self.yum.install_pkg_cmd()} wget
        wget https://downloads.mariadb.com/MariaDB/mariadb_repo_setup -O mariadb_repo_setup
        chmod +x mariadb_repo_setup
        ./mariadb_repo_setup --mariadb-server-version="{self.config.release}" --skip-maxscale --skip-tools
        {self.yum.install_pkg_cmd()} perl-DBI libaio libsepol lsof boost-program-options
        {self.yum.install_pkg_cmd()} libpmem galera-4.x86_64 || true
        {self.yum.enable_repo_cmd()}=mariadb-main clean metadata
        {self.yum.install_pkg_cmd()} MariaDB-server MariaDB-client
        """
        self.run(cmd)
