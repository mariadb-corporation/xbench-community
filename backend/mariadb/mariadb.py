# -*- coding: utf-8 -*-
# Copyright (C) 2022 dvolkov


import os
from dataclasses import asdict

from common import round_down_to_even
from compute import Node
from compute.backend_product import BackendProduct
from compute.backend_target import BackendTarget
from lib import XbenchConfig
from lib.file_template import FileTemplate, FileTemplateException

from ..abstract_backend import AbstractBackend
from ..base_backend import SingleManagedBackend
from ..base_mysql_backend import BaseMySqlBackend
from .exceptions import MariaDBException
from .mariadb_config import MariaDBConfig

MARIADB_CONFIG_FILE = "mariadb.yaml"
MARIADB_OS_USER = "mysql"
SERVER_CONFIG_DIR = "/etc/my.cnf.d"
SERVER_CONFIG_FILE = f"{SERVER_CONFIG_DIR}/server.cnf"
CERTS_DIRECTORY = f"{SERVER_CONFIG_DIR}/certificates"


class MariaDB(SingleManagedBackend, BaseMySqlBackend, AbstractBackend):
    """Generic class for MariaDB"""

    clustered = False
    product = BackendProduct.mariadb

    def __init__(
        self,
        node: Node,
        **kwargs,
    ):
        SingleManagedBackend.__init__(
            self,
            node=node,
            backend_config_yaml_file=MARIADB_CONFIG_FILE,
            backend_config_klass=MariaDBConfig,
            **kwargs,
        )
        BaseMySqlBackend.__init__(self, bt=self.config.db)

    def download(self):
        """This method has to be implemented in the upcoming classes"""

    def set_mariadb_config(self):
        """Set up mariadb config file (cnf)"""

        cmd = f"""
        mkdir -p {SERVER_CONFIG_DIR}
        cat << EOF > /etc/my.cnf
        [mariadb]
        !includedir {SERVER_CONFIG_DIR}
        EOF
        """
        self.run(cmd)

        # Let's get system resources
        memory_mb = self.node.memory_mb
        # Buffer pool size is (80% * RAM) but not larger than (RAM-4G)
        buffer_pool_size = round_down_to_even(
            min(0.8 * memory_mb, memory_mb - 4 * 1024)
        )
        try:
            # Let's get template
            ft = FileTemplate(filename=self.config.cnf_template)
            # and render it
            params = {
                "mariadb": asdict(self.config.db),
                "system": {
                    "buffer_pool_size": buffer_pool_size,  # In MB
                },
                "config": asdict(self.config),
            }
            config = ft.render(**params)
            # this is a way to put it to the file without scp to temp directory and then rename
            cmd = f"""
            cat << EOF > {SERVER_CONFIG_FILE}
            {config}
            EOF
            """
            self.run(cmd)
        except FileTemplateException as e:
            raise MariaDBException(e)

    def copy_certs(self):
        """Copy certs from xbench vault to the MariaDB Server"""

        if self.config.db.ssl is not None:
            cmd = f"""
            mkdir -p {CERTS_DIRECTORY}
            chown -R mysql:mysql {CERTS_DIRECTORY}
            """
            self.run(cmd)
            for _, file in self.config.db.ssl.items():
                self.node.send_file(file, f"{CERTS_DIRECTORY}/{os.path.basename(file)}")

    def configure(self):
        SingleManagedBackend.configure(self)
        dir = self.config.data_dir
        cmd = f"""
        adduser mysql
        rm -rf /var/lib/mysql
        ln -s {dir} /var/lib/mysql
        chown -R mysql:mysql /var/lib/mysql
        chown -R mysql:mysql {dir}
        chmod -R 755 {dir}
        """
        self.run(cmd=cmd)
        self.copy_certs()

    # TODO Huge pages!!!
    # hugeadm from ibhugetlbfs-utils.x86_64
    # TODO - skip anonymous user
    def install(self) -> BackendTarget:
        self.download()
        self.logger.info("Running MariaDB installer...")
        # From https://mariadb.com/kb/en/mysql_install_db/
        #  sudo -u mysql mariadb-install-db --defaults-file=/etc/my.cnf.d/server.cnf --user=mysql  --basedir=/usr --datadir=/data/mariadb --skip-test-db
        self.set_mariadb_config()
        dir = self.config.data_dir
        cmd = f"""
        rm -rf {dir}/*
        mariadb-install-db --defaults-file={SERVER_CONFIG_FILE} --auth-root-authentication-method=socket --user={MARIADB_OS_USER} --basedir=/usr --datadir={self.config.data_dir} --skip-test-db
        """
        self.run(cmd)

        self.start()
        self.create_database_and_user()

        if self.config.globals:
            self.set_globals()

        if self.config.enable_prometheus_exporter:
            self.install_exporter()

        self.db_connect()
        self.print_db_version()
        # BT target is for drivers, so we need to re-adjust how drivers are going to connect
        self.config.db.host = self.node.vm.network.get_client_iface()
        return self.config.db

    def clean(self):
        self.stop()
        dir = self.config.data_dir
        cmd = f"""
        rm -rf {dir}/*
        """
        self.run(cmd)
        # TODO clean packages
        # pm_r = self.yum.remove_pkg_cmd()

        self.run("pkill -9 mysqld_exporter")

    def start(self, **kwargs):
        cmd = "systemctl start mariadb"
        self.run(cmd=cmd)

    def stop(self, **kwargs):
        cmd = "systemctl stop mariadb"
        self.run(cmd=cmd)

    # TODO
    # Set global http://storage02.colo.sproutsys.com/pub/qa/performance/log/XL/vm2-ES-16/220414.185236.aws.scaleout/220414.185421609.build.cluster/220414.185421626.build.mariadb.vm2-ES-16.log

    def install_exporter(self):
        self.node.ssh_client.send_files(
            f"{XbenchConfig().xbench_home()}/metrics/exporters/mysqld_exporter", "./"
        )
        mysql_cmd = f"""
        CREATE USER IF NOT EXISTS'exporter'@'%' IDENTIFIED BY '{self.config.db.password}' WITH MAX_USER_CONNECTIONS 3;
        GRANT SUPER, PROCESS, REPLICATION CLIENT, SELECT ON *.* TO 'exporter'@'%';
        flush privileges;
        """
        self.run(self.mysql_cli(mysql_cmd))
        exporter_cmd = f"""
        export DATA_SOURCE_NAME="exporter:{self.config.db.password}@(localhost:{self.config.db.port})/";
        ./mysqld_exporter > exporter.log 2>&1 &
        """
        self.run(exporter_cmd)
        self.node.register_metric_target(
            service_name="mariadb_exporter", port=self.config.prometheus_port
        )

    def get_logs(self):
        pass
