# -*- coding: utf-8 -*-
# Copyright (C) 2022 dvolkov

from compute import Node

from .mariadb import MariaDB

MARIADB_RUN_COMMAND_TIMEOUT = 600  # single command should't take longer
MARIADB_CONFIG_FILE = "mariadb.yaml"


class MariaDBEnterprise(MariaDB):
    """Generic class for Xpand"""

    def __init__(
        self,
        node: Node,
        **kwargs,
    ):
        super(MariaDBEnterprise, self).__init__(node, **kwargs)

    def download(self):
        """
        https://mariadb.com/docs/reference/repo/cli/mariadb_es_repo_setup/
        """
        self.logger.info("Downloading MariaDB...")
        cmd = f"""
        {self.yum.install_pkg_cmd()} wget
        wget https://dlm.mariadb.com/enterprise-release-helpers/mariadb_es_repo_setup -O mariadb_es_repo_setup
        chmod +x mariadb_es_repo_setup
        ./mariadb_es_repo_setup --token="{self.config.enterprise_download_token}" --apply --mariadb-server-version="{self.config.release}" --skip-maxscale --skip-tools
        {self.yum.install_pkg_cmd()} MariaDB-server MariaDB-client
        """
        self.run(cmd)
