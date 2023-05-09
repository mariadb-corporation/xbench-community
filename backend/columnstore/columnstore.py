# -*- coding: utf-8 -*-
# Copyright (C) 2021 detravi


import json

import os
from dataclasses import asdict
from typing import Dict, List

from backend.mariadb import MariaDB, MariaDBEnterprise
from backend.base_backend import BaseBackend

from compute import BackendTarget, MultiNode, Node
from compute.yum import Yum
from dacite import from_dict
from lib import XbenchConfig
from lib.mysql_client import MySqlClient, MySqlClientException
from pathlib import Path

from ..abstract_backend import AbstractBackend
from .aws_cli import get_aws_cli
from .columnstore_config import ColumnStoreConfig

from .exceptions import ColumnstoreException
from .packages import get_engine_drone_build_bucket, get_cmapi_build_bucket, split_build_tokens
from .config_templates import mcs_cluster_cnf, util_query, repl_query, slave_replica_users_query, engineering_repo


COLUMNSTORE_CONFIG_FILE = "columnstore.yaml"
CMAPI_KEY = "xbench-api-key"
COLUMSTORE_PATH = "/var/lib/columnstore"

class ColumnStore(AbstractBackend,BaseBackend, MultiNode, MySqlClient):
    """Generic class for ColumnStore"""

    clustered = True

    def set_data_dir(self, mariadb_data_dir):
        parent_dir = os.path.dirname(os.path.normpath(mariadb_data_dir))
        if parent_dir == "/":
            raise ColumnstoreException("MariaDB data path should be at least two level deep for Columnstore installation")
        self.columnstore_data_dir = os.path.join(parent_dir, "columnstore")


    def __init__(self, nodes: List[Node], **kwargs, ):
        MultiNode.__init__(self, nodes)
        self.cs_config_label = self.head_node.vm.klass_config_label
        self.logger.debug(f"Using {self.cs_config_label} for ColumnStore installation")

        BaseBackend.__init__(
            self,
            COLUMNSTORE_CONFIG_FILE,
            self.cs_config_label,
            backend_config_klass=ColumnStoreConfig,
            **kwargs,
        )

        self.yum = Yum(os_type=self.head_node.vm.os_type)
        if self.config.build == "enterprise":
            self.maria_servers = [
                MariaDBEnterprise(node, mount_storage_to_parent=True, override_config_klass_label='latest', )
                for node in self.nodes]
        else:
            self.maria_servers = [
                MariaDB(node, mount_storage_to_parent=True, override_config_klass_label='latest')
                for node in self.nodes]

        self.conf_file = "/etc/columnstore/Columnstore.xml"
        self.storagemanager_conf_file = "/etc/columnstore/storagemanager.cnf"
        self.set_data_dir(self.maria_servers[0].config.data_dir)
        self.config.db.host = self.head_node.vm.network.get_public_iface()
        MySqlClient.__init__(self, **asdict(self.config.db))


    def install_columnstore_from_es_repo(self):
        self.logger.info("Installing columnstore from ES Repository")

        cmd = (f"{self.yum.install_pkg_cmd()} "
           "MariaDB-columnstore-cmapi "
           "MariaDB-columnstore-engine "
           "MariaDB-columnstore-engine-debuginfo"
         )
        self.run_on_all_nodes(cmd)


    def install_columnstore_from_link_in_env(self):
        self.logger.info(
                        (f"Installing jenkins columnstore from {self.config.mcs_baseurl} and "
                         f"CMAPI from {self.config.cmapi_baseurl}"))

        engineering_repo_config = engineering_repo.format(
            mcs_baseurl=self.config.mcs_baseurl,
            cmapi_baseurl=self.config.cmapi_baseurl
        )

        self.run_on_all_nodes(f'cat << EOF > /etc/yum.repos.d/engineering.repo\n \
                              {engineering_repo_config}', sudo=True)


        cmd = (f"{self.yum.install_pkg_cmd()} "
            "MariaDB-shared "
            "MariaDB-client "
            "MariaDB-server "
            "MariaDB-backup "
            "MariaDB-spider-engine "
            "MariaDB-cracklib-password-check "
            "MariaDB-columnstore-engine  "
            "MariaDB-columnstore-cmapi "
        )

        self.run_on_all_nodes(cmd)

    def install_columnstore_from_local(self):
        self.logger.info(f"Installing local columnstore from {self.config.packages_path}")

        pathlist = Path(self.config.packages_path).glob(f'*.{self.yum.package_file_extension()}')
        if not pathlist:
            raise ColumnstoreException(
                (f"Chosen Columnstore installation from local {self.config.packages_path},"
                 f"but this path doesn't contain any {self.yum.package_file_extension()} files"))

        install_path = "/tmp"

        self.scp_to_all_nodes(self.config.packages_path, install_path, recursive=True)
        package_path = os.path.join(install_path, os.path.basename(os.path.normpath(self.config.packages_path)))
        self.run_on_all_nodes(self.yum.install_pkg_cmd() + f" {package_path}/*.{self.yum.package_file_extension()}")


    def install_all_from_drone_artifacts(self):
        self.logger.info(f"Installing Drone built columnstore {self.config.branch} from {self.config.build}")

        def get_aws_commands(install_path, os, arch):
            cli = get_aws_cli()

            engine_bucket = get_engine_drone_build_bucket(branch = self.config.branch,
                                                          arch = arch,
                                                          server_version = self.config.server_version,
                                                          os = os,
                                                          build = self.config.build)

            cmapi_bucket = get_cmapi_build_bucket(branch = self.config.branch,
                                                  arch = arch,
                                                  build = self.config.build)

            aws_cmd = f'export PATH=$PATH:/usr/local/bin && {cli.get_base_command()} s3 cp'
            r = (f'{aws_cmd} {engine_bucket} {install_path} --recursive --exclude "*" --include "*.rpm"',
                 f'{aws_cmd} {cmapi_bucket} {install_path} --recursive --exclude "*" --include "*.rpm"')

            return r

        self.install_path = f"/tmp/columnstore_install/{self.config.branch}"

        self.run_on_all_nodes(f'{self.yum.install_pkg_cmd()} python3-pip')
        self.run_on_all_nodes("pip3 install awscli")
        self.run_on_all_nodes(f"mkdir -p {self.install_path}")
        self.run_on_all_nodes(f"rm -rf {self.install_path}/*")

        for command in get_aws_commands(self.install_path,
                                        self.head_node.vm.os_type,
                                        self.head_node.vm.arch):
            self.run_on_all_nodes(command)

        self.run_on_all_nodes(f'{self.yum.install_pkg_cmd()} {self.install_path}/*.rpm')
        self.run_on_all_nodes(f"chown -R -L mysql:mysql {COLUMSTORE_PATH}")


    def configure_replication(self):
        self.logger.info(f"Configuring replication")
        for id_num, node in enumerate(self.nodes, 1):
            node.run(f'cat << EOF > /etc/my.cnf.d/mcs-cluster.cnf\n \
                     {mcs_cluster_cnf.format(server_id=id_num)}', sudo=True)

        self.run_on_all_nodes("grep -rl skip-log-bin /etc/my.cnf.d/ | xargs sed -i 's/skip-log-bin/#skip-log-bin/g'")
        self.run_on_all_nodes("systemctl restart mariadb");

        dbpassword = self.maria_servers[0].config.db.password
        repl_user="repl"
        util_user = "util_user"

        self.logger.info(f"Configuring util user")
        util_user_query = util_query.format(
                util_user = util_user,
                util_password = dbpassword,
        )
        self.maria_servers[0].run(self.maria_servers[0].mysql_cli(util_user_query))



        self.logger.info(f"Configuring replication: setting up master")
        for node in self.nodes[1:]:
            slave_host = node.run("hostname").strip()
            self.logger.info(f"Adding access for user {repl_user}@{slave_host}")
            repl_user_query=repl_query.format(
                repl_user = repl_user,
                repl_password = dbpassword,
                slave_host = slave_host
            )
            self.maria_servers[0].run(self.maria_servers[0].mysql_cli(repl_user_query))



        self.logger.info(f"Configuring replication: setting up slaves")
        slave_query=slave_replica_users_query.format(master_host = self.head_node.vm.network.private_ip,
                                                     repl_user = repl_user,
                                                     repl_password = dbpassword)
        for server in self.maria_servers[1:]:
            server.run(server.mysql_cli(slave_query))

        self.logger.info(f"Configuring crossengine support")
        for node in self.nodes:
            node.run('mcsSetConfig CrossEngineSupport Host 127.0.0.1', sudo=True)
            node.run(f'mcsSetConfig CrossEngineSupport Password {dbpassword}', sudo=True)
            node.run(f'mcsSetConfig CrossEngineSupport User {util_user}', sudo=True)

        self.run_on_all_nodes("systemctl restart mariadb");


    def configure(self):
        for maria in self.maria_servers:
            maria.configure()

        self.run_on_all_nodes(f"mkdir -p {self.columnstore_data_dir}")
        self.run_on_all_nodes(f"rm -rf {COLUMSTORE_PATH}")
        self.run_on_all_nodes(f"ln -s {self.columnstore_data_dir} {COLUMSTORE_PATH} ")
        self.run_on_all_nodes(f"chown -R -L mysql:mysql {self.columnstore_data_dir}")
        self.run_on_all_nodes(f"chown -R -L mysql:mysql {COLUMSTORE_PATH}")
        self.run_on_all_nodes(f"chmod 755 {self.columnstore_data_dir}")

        self.cluster_name = XbenchConfig().cluster_name()
        self.logger.info(f"Columnstore will be configured for S3bucket '{self.cluster_name}'")
        self.logger.info(f"Columnstore will use {self.columnstore_data_dir} as datadir")


    def install(self) -> BackendTarget:
        self.logger.info(f"Columnstore will install {self.config.build}")
        self.run_on_all_nodes(f'{self.yum.install_pkg_cmd()} curl jq')


        if self.config.build not in ("local", "enterprise", "jenkins"):
            self.install_all_from_drone_artifacts()

        if self.config.build == "local":
            self.install_columnstore_from_local()

        if self.config.build == "jenkins":
            self.install_columnstore_from_link_in_env()

        # if build is not enterprise, install methods for maria are empty
        # otherwise, it will install MariDB server, and we install columnstore plugin after
        for maria in self.maria_servers:
            maria.install()

        if self.config.build == "enterprise":
            self.install_columnstore_from_es_repo()


        self.run_on_all_nodes(f"chown -R -L mysql:mysql {self.columnstore_data_dir}")
        self.run_on_all_nodes(f"chown -R -L mysql:mysql {COLUMSTORE_PATH}")
        self.run_on_all_nodes(f"chmod 755 {self.columnstore_data_dir}")

        self.configure_replication()

        self.start()

        for ip in self._all_client_ips():
            self.head_node.run(f"""curl -k -s -X 'PUT' https://127.0.0.1:8640/cmapi/0.4.0/cluster/node \
                                   --header 'Content-Type:application/json' \
                                   --header 'x-api-key:{CMAPI_KEY}' \
                                   --data '{{"timeout":120, "node": ip }}'""", sudo=True)



        self.config.db.host = ",".join(self._all_client_ips())
        return self.config.db


    def db_connect(self):
        try:
            self.connect()
        except MySqlClientException as e:
            raise ColumnstoreException(e)


    def self_test(self):
        results = self.run_on_all_nodes(f"""curl -k https://127.0.0.1:8640/cmapi/0.4.0/cluster/status \
                                            --header 'Content-Type:application/json' \
                                            --header 'x-api-key:{CMAPI_KEY}' | jq . """, sudo=True)

        for result in results:
            cluster_statuses = []
            status = json.loads(result["stdout"])
            for ip in self._all_client_ips():
                if not ip in status:
                    raise ColumnstoreException(f"Node {ip} is not shown by cluster status")
                if status["num_nodes"] != len(self.nodes):
                    raise ColumnstoreException(f"Incorrect number of nodes: {status['num_nodes']}, expected {len(self.nodes)}")

                cluster_status = status[ip]['dbrm_mode']
                cluster_statuses.append(cluster_status == "master")
                cluster_mode = status[ip]['cluster_mode']

                if cluster_status == "master" and cluster_mode != "readwrite":
                    raise ColumnstoreException(f"Master node {ip} is in {cluster_mode} mode, readwrite expected")

                if cluster_status == "slave" and cluster_mode != "readonly":
                    raise ColumnstoreException(f"Slave node {ip} is in {cluster_mode} mode, readonly expected")

            if not any(cluster_statuses):
                raise ColumnstoreException(f"Master node missing in cluster status on node {ip}")


    def clean(self):
        self.stop()
        self.run_on_all_nodes(cmd=f"rm -rf {COLUMSTORE_PATH}", sudo=True)
        self.run_on_all_nodes(cmd=f"rm -rf {self.columnstore_data_dir}", sudo=True)

        for maria in self.maria_servers:
            maria.clean()

        self.run_on_all_nodes(cmd="yum list --installed | grep MariaDB | xargs yum remove -y")


    def start(self, **kwargs):
        for maria in self.maria_servers:
            maria.start()

        self.run_on_all_nodes(cmd="systemctl start mariadb-columnstore-cmapi")


    def stop(self, **kwargs):
        self.head_node.run(f"""curl -k -s -X PUT https://mcs1:8640/cmapi/0.4.0/cluster/shutdown \
                               --header 'Content-Type:application/json' \
                               --header 'x-api-key:{CMAPI_KEY}' \
                               --data '{{"timeout": 120}}' """, sudo=True)

        for maria in self.maria_servers:
            maria.stop()

        self.run_on_all_nodes(cmd="systemctl stop mariadb-columnstore-cmapi")


    def post_data_load(self, database: str):
        pass


    def pre_workload_run(self):
        pass


    def pre_thread_run(self):
        pass


    def print_db_size(self, database: str) -> None:
        query = f"call columnstore_info.total_usage();"
        row = self.select_one_row(query)
        self.logger.info(
            f"Total Database ({database}) size: \n{row.get('TOTAL_DATA_SIZE')} (GB)"
        )

    def get_logs(self):
        pass
