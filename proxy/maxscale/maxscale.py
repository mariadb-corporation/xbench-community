# -*- coding: utf-8 -*-
# Copyright (C) 2022 dvolkov


import logging
from dataclasses import asdict
from typing import List

from compute import MultiNode, Node
from compute.backend_target import BackendTarget
from compute.yum import Yum
from dacite import from_dict
from lib import XbenchConfig
from lib.file_template import FileTemplate, FileTemplateException
from lib.mysql_client import MySqlClient, MySqlClientException

from ..abstract_proxy import AbstractProxy
from .exceptions import MaxscaleException
from .maxscale_config import MaxscaleConfig

MAXSCALE_RUN_COMMAND_TIMEOUT = 600  # single command should't take longer
MAXSCALE_CONFIG_FILE = "maxscale.yaml"
MAXSCALE_OS_USER = "mysql"
MAXSCALE_CNF_FILE = "/etc/maxscale.cnf"


class Maxscale(AbstractProxy, MultiNode, MySqlClient):
    """Generic class for MariaDB"""

    clustered = True

    def __init__(
        self,
        nodes: List[Node],
        **kwargs,
    ):

        MultiNode.__init__(self, nodes)

        self.maxscale_config_label = self.head_node.vm.klass_config_label

        self.maxscale_config = from_dict(
            MaxscaleConfig,
            data=XbenchConfig().get_key_from_yaml(
                yaml_file_name=MAXSCALE_CONFIG_FILE,
                key_name=self.maxscale_config_label,
                use_defaults=True,
            ),
        )

        self.yum = Yum(os_type=self.head_node.vm.os_type)
        # I should be able to connect to maxscale
        self.maxscale_config.db.host = ",".join(self._all_public_ips())
        MySqlClient.__init__(self, **asdict(self.maxscale_config.db))

    def configure(self):
        self.logger.info("Running MaxScale configure")
        self.download()

    def download(self):
        """Implements enterprise version only.
        https://mariadb.com/kb/en/mariadb-package-repository-setup-and-usage/
        https://mariadb.com/docs/reference/repo/cli/mariadb_es_repo_setup/
        """
        cmd = f"""
        wget https://dlm.mariadb.com/enterprise-release-helpers/mariadb_es_repo_setup -O mariadb_es_repo_setup
        chmod +x mariadb_es_repo_setup
        ./mariadb_es_repo_setup --token="{self.maxscale_config.enterprise_download_token}" --apply --mariadb-maxscale-version="{self.maxscale_config.release}"
        """
        self.run_on_all_nodes(cmd)

    # TODO Maxscale user can be different from driver/xbench user
    def install(self):
        """_summary_

        https://mariadb.com/kb/en/mariadb-maxscale-6-setting-up-mariadb-maxscale/

        Returns:
            BackendTarget: _description_
        """
        self.download()
        self.logger.info("Running Maxscale installer...")

        cmd = f"{self.yum.install_pkg_cmd()} maxscale"
        self.run_on_all_nodes(cmd)

    # TODO https://mariadb.com/kb/en/mariadb-maxscale-6-setting-up-mariadb-maxscale/#creating-a-user-account-for-maxscale
    def post_install(self, bt: BackendTarget) -> BackendTarget:
        """This is called from provisioning after all components has been installed"""
        self.set_maxscale_config(bt)
        self.start()
        # TODO Prometheus exporter

        # BT target is for drivers, so we need to re-adjust how drivers are going to connect
        bt.host = ",".join(self._all_client_ips())
        # self.db_connect()
        return bt

    def get_version(self):
        cmd = "maxctrl --version"
        return self.run_on_one_node(cmd)

    # TODO: enable_root_user¶
    def set_maxscale_config(self, bt: BackendTarget):
        """
        https://mariadb.com/kb/en/mariadb-maxscale-6/maxscale-configuration-usage-scenarios/
        https://mariadb.com/kb/en/mariadb-maxscale-6-mariadb-maxscale-configuration-guide/
        https://mariadb.com/kb/en/mariadb-maxscale-6-xpand-monitor/
        """
        try:
            # Let's get template
            ft = FileTemplate(filename=self.maxscale_config.cnf_config_template)

            # and render it
            bt.host = bt.host.split(",")[0]  # First Xpand node
            params = {"xpand": asdict(bt), "maxscale": asdict(self.maxscale_config.db)}
            config = ft.render(**params)

            # this is a way to put it to the file without scp to temp directory and then rename
            cmd = f"""
            cat << EOF > {MAXSCALE_CNF_FILE}
            {config}
            EOF
            """
            self.run_on_all_nodes(cmd)
        except FileTemplateException as e:
            raise MaxscaleException(e)

    @staticmethod
    def mysql_cli(cmd):
        """Simplify running multiply command via mysql command line"""
        return f"""mysql -A -s << EOF
        {cmd.replace("'", '"')}
        EOF
        """

    def db_connect(self):
        try:
            self.connect()
            self.print_db_version()
        except MySqlClientException as e:
            raise MaxscaleException(e)

    def self_test(self):
        # systemctl status maxscale.service
        cmd = "maxctrl list servers"
        output = self.run_on_all_nodes(cmd)
        for o in output:
            self.logger.info(f"{o.get('hostname')}\n{o.get('stdout')}")

        # maxctrl list servers | grep XpandMonitor:node | grep -i Running | wc -l
        # sudo systemctl status maxscale --no-pager

        pass

    def clean(self):
        self.stop()
        cmd = """
        rm -rf /var/log/maxscale
        rm -rf mariadb_es_repo_setup*
        rm -f /etc/yum.repos.d/mariadb.repo
        yum -y remove maxscale
        """
        self.run_on_all_nodes(cmd=cmd)

    def start(self, **kwargs):
        cmd = "systemctl start maxscale"
        self.run_on_all_nodes(cmd=cmd)

    def stop(self, **kwargs):
        cmd = "systemctl stop maxscale"
        self.run_on_all_nodes(cmd=cmd)
