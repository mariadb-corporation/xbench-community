# -*- coding: utf-8 -*-
# Copyright (C) 2022 dvolkov


import os
from dataclasses import asdict

from common import round_down_to_even
from compute import Node
from compute.backend_dialect import BackendDialect
from compute.backend_product import BackendProduct
from compute.backend_target import BackendTarget
from lib import XbenchConfig
from lib.file_template import FileTemplate, FileTemplateException

from ..abstract_backend import AbstractBackend
from ..base_backend import SingleManagedBackend
from ..base_mysql_backend import BaseMySqlBackend
from .exceptions import MySqlDBException
from .mysql_config import MySqlDBConfig

MYSQL_MAJOR_VERSION="80"
MYSQL_CONFIG_FILE = "mysql.yaml"
MYSQL_OS_USER = "mysql"

SERVER_CONFIG_DIR = "/etc/my.cnf.d"
SERVER_CONFIG_FILE = f"{SERVER_CONFIG_DIR}/my.cnf"
CERTS_DIRECTORY = f"{SERVER_CONFIG_DIR}/certificates"


class MySQLServer(SingleManagedBackend, BaseMySqlBackend, AbstractBackend):
    """Implements MySQL Community"""

    clustered = False
    dialect = BackendDialect.mysql
    product = BackendProduct.mysql

    def __init__(
        self,
        node: Node,
        **kwargs,
    ):
        SingleManagedBackend.__init__(
            self,
            node=node,
            backend_config_yaml_file=MYSQL_CONFIG_FILE,
            backend_config_klass=MySqlDBConfig,
        )
        BaseMySqlBackend.__init__(self, bt=self.config.db)

    def download(self):
        """ This method will install the package """

        # Version 8 already has mysql, it need to be disabled
        if self.yum.version_number() == '8':
            cmd = f"""{self.yum.disable_module_cmd()} mysql"""
            self.run(cmd)

        cmd = f"""
        wget https://repo.mysql.com/mysql80-community-release-el{self.yum.version_number()}.rpm
        {self.yum.install_local_pkg_cmd()} mysql{MYSQL_MAJOR_VERSION}-community-release-el{self.yum.version_number()}.rpm
        {self.yum.enable_repo_cmd()}=mysql{MYSQL_MAJOR_VERSION}-community clean metadata
        {self.yum.install_pkg_cmd()} mysql*{self.config.release}*
        """
        self.run(cmd=cmd)

    def set_mysql_config(self):
        """Set up mariadb config file (cnf)"""

        cmd = f"""
        mkdir -p {SERVER_CONFIG_DIR}
        cat << EOF > /etc/my.cnf
        [{self.product}]
        !includedir {SERVER_CONFIG_DIR}
        EOF
        """
        self.run(cmd)

        # Let's get system resources
        memory_mb = self.node.memory_mb
        # Buffer pool size is (80% * RAM) or (RAM-10G), whichever is larger
        buffer_pool_size = round_down_to_even(
            max(0.8 * memory_mb, memory_mb - 10 * 1024)
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
            raise MySqlDBException(e)

    def copy_certs(self):
        """Copy certs from xbench vault to the MariaDB Server"""

        cmd = f"""
        mkdir -p {CERTS_DIRECTORY}
        chown -R mysql:mysql {CERTS_DIRECTORY}
        """
        self.run(cmd)

        local_certs_dir = self.xbench_config.get("certs_dir")

        for file in ["server-cert.pem", "server-key.pem", "ca.pem"]:
            self.node.send_file(
                os.path.join(local_certs_dir, file), f"{CERTS_DIRECTORY}/{file}"
            )

    def configure(self):
        SingleManagedBackend.configure(self)
        dir = self.config.data_dir
        cmd = f"""
        adduser {MYSQL_OS_USER}
        rm -rf /var/lib/{MYSQL_OS_USER}
        ln -s {dir} /var/lib/{MYSQL_OS_USER}
        chown -R mysql:mysql /var/lib/{MYSQL_OS_USER}
        chown -R {MYSQL_OS_USER}:{MYSQL_OS_USER} {dir}
        chmod -R 755 {dir}
        """
        self.run(cmd=cmd)

    # TODO Huge pages!!!
    # hugeadm from ibhugetlbfs-utils.x86_64
    # TODO - skip anonymous user


    def install(self) -> BackendTarget:
        self.download()
        self.logger.info(f"Running {self.product} installer...")
        self.set_mysql_config()
        dir = self.config.data_dir
        # mysql-install-db is not supported anymore
        # TODO change root password: ALTER USER 'root'@'localhost' IDENTIFIED BY 'root-password';
        # Check for --skip-name-resolve[={OFF|ON}]
        cmd = f"""
        rm -rf {dir}/*
        mysqld --defaults-file={SERVER_CONFIG_FILE} --user={MYSQL_OS_USER} --basedir=/usr --datadir={self.config.data_dir}  --initialize-insecure
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
        cmd = f"systemctl start mysqld"
        self.run(cmd=cmd)

    def stop(self, **kwargs):
        cmd = f"systemctl stop mysqld"
        self.run(cmd=cmd)

    #TODO implement the method
    def print_non_default_variables(self):
        pass

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
            service_name=f"{self.product}_exporter", port=self.config.prometheus_port
        )
