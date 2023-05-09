import logging
import os
import tempfile
from typing import Optional

import yaml
from dacite import from_dict

from backend.base_backend import mkdir_command
from common.common import round_down_to_even
from compute import BackendTarget, Node
from lib import PgSqlClient, PgSqlClientException, XbenchConfig

from ..abstract_proxy import AbstractProxy
from .exceptions import XgresException
from .xgres_config import XgresConfig

XGRES_CONFIG_FILE = "xgres.yaml"

# TODO: type annotations
# TODO: logging
# TODO: install from upstream repos instead of building from source
# TODO: refactor by inheriting backend.postgresql.PostgreSQLDB or something like it
class Xgres(AbstractProxy):
    """
    build and install postgres and our xgres foreign data wrapper

    the project will be installed and run in /opt/xgres
    /opt/xgres/postgresql -> our build of the postgresql database
    /opt/xgres/xgres -> our build of the FDW
    /opt/xgres/mdbinstall -> our installation of postgres with our FDW installed

    as a stateless proxy, the location of the log and data files for this
    postgres install are much less critical, so we don't have to ensure that
    we are using the best available io devices

    while there are discussions about adding multiple postgres proxies in
    the future, for now this class is only going to work with a single proxy
    until the FDW supports multiple pg instances

    This project was built and tested only on CentOS 7 and GCC 4.8, so for expediency
    we are going to limit this class to working with CentOS7 beacuse we not only
    have to run postgres with our fdw, but we also have to build them from source.
    """

    clustered = False

    def __init__(self, node: Node, **kwargs):
        self.node = node
        self.logger = logging.getLogger(__name__)
        self.project_directory = "/data/xgres"
        self.database_directory = f"{self.project_directory}/mdbinstall"
        self.custom_settings_file = f"{self.database_directory}/data/custom.conf"
        # Postgres tuning
        # max_connections = self.node.nproc * 8 + 10
        # shared_buffers = round_down_to_even(self.node.memory_mb / 4)
        # work_mem = round_down_to_even(shared_buffers / max_connections)
        # effective_cache_size = round_down_to_even(self.node.memory_mb * 0.75)
        # max_worker_processes = self.node.nproc

        # Fixed settings for 16 cpu 64 Gb of memory for now
        max_connections = 1024
        shared_buffers = 15852
        work_mem = 114
        effective_cache_size = 47558
        max_worker_processes = 16

        self.custom_settings = "\n".join(
            [
                "listen_addresses = '*'",
                "shared_preload_libraries = '$libdir/xgres.so'",
                f"max_connections = {max_connections}",
                f"shared_buffers = {shared_buffers}",
                f"work_mem = {work_mem}",
                f"effective_cache_size = {effective_cache_size}",
                f"max_worker_processes = {max_worker_processes}",
                "plan_cache_mode = force_generic_plan",
            ]
        )

        self.xgres_config = from_dict(
            XgresConfig,
            data=XbenchConfig().get_key_from_yaml(
                yaml_file_name=XGRES_CONFIG_FILE,
                key_name=self.node.vm.klass_config_label,
                use_defaults=True,
            ),
        )

        # This is a reserved naming convention in XGRES code
        self.public_server_option = (
            "xpand_server"
            if self.xgres_config.xgres_query_path == "FDW"
            else "xpand_server_global"
        )

        self.xgres_config.db.host = self.node.vm.network.get_private_iface()

        self.pg_client = PgSqlClient(
            host=self.node.vm.network.get_public_iface(),
            port=self.xgres_config.db.port,
            user=self.xgres_config.db.user,
            password=self.xgres_config.db.password,
            database=self.xgres_config.db.database,
        )

    @staticmethod
    def _local_psql(stmt: str):
        """
        some commands must be run locally connecting to the postgres socket
        as the postgres user
        """
        return f"""sudo -i -u postgres $SHELL -c 'psql' << EOF
        {stmt}
        EOF
        """

    def psql(self, stmt: str):
        """
        use the remote client
        """
        self.logger.debug(f"executing '{stmt}' on {self.pg_client.host}")
        self.pg_client.execute(stmt)

    def _clone_repo_cmd(self, repo_name: str, target_dir: Optional[str] = "") -> str:
        return (
            "git clone"
            f" https://{self.xgres_config.xgres_git_token}@github.com/mariadb-corporation/{repo_name}.git {target_dir}"
        )

    def _make_project_directory(self):
        # TODO uses proper backend class and not hardcoded devices
        cmd = mkdir_command(
            directory="/data", device="/dev/nvme1n1", mount_to_parent=False
        )  # TODO check mount_for_parent
        self.node.run(cmd, sudo=True)
        self.node.run(f"mkdir -p {self.project_directory}", sudo=True)
        self.node.run(f"chown -R postgres:postgres {self.project_directory}", sudo=True)

    def _manage_packages(self, action: str):
        if action == "install":
            action = self.node.yum.install_pkg_cmd()
            group_action = self.node.yum.install_group()
        else:
            action = self.node.yum.remove_pkg_cmd()
            group_action = self.node.yum.remove_group()

        for pkg in (
            "zlib-devel",
            "readline-devel",
            "mariadb-devel",
            "libzstd",
        ):
            self.node.run(f"{action} {pkg}", sudo=True)
        os_major_version = self.node.os_version.split(".")[0]
        arch = self.node.vm.arch
        self.node.run(
            f"{action} https://download.postgresql.org/pub/repos/yum/reporpms/EL-{os_major_version}-{arch}/pgdg-redhat-repo-latest.noarch.rpm",
            sudo=True,
        )
        # accept GPG keys for pg repos
        # this project was built on postgres 14, so we are hard coding it here
        # until we know that it would work on other versions
        if action == "install":
            # the versions of postgres that come with standard repos are almost always way too old
            # we need to disable the existing postgres module so that we instead install from the pgdg repo
            if self.node.yum.version_number() == "8":
                self.node.run(f"{self.node.yum.disable_module_cmd()} postgresql")
            self.node.run("yes | yum install postgresql14 -y", sudo=True)
        elif action == "erase":
            self.node.run(f"{action} postgresql14", sudo=True)
        self.node.run(f"{action} libpq5-devel", sudo=True)
        self.node.run(f'{group_action} "Development Tools" --nobest', sudo=True)

    def _setup_pg_bash_profile(self):
        pg_bash_pro = f"""
# .bash_profile

# Get the aliases and functions
if [ -f ~/.bashrc ]; then
    . ~/.bashrc
fi

# User specific environment and startup programs

PATH=$PATH:$HOME/.local/bin:$HOME/bin

export PATH
export PGHOME={self.database_directory}/data
export PATH={self.database_directory}/bin:$PATH
export LD_LIBRARY_PATH={self.database_directory}/lib:$LD_LIBRARY_PATH\n"""
        with tempfile.NamedTemporaryFile("r+") as tmp:
            tmp.write(pg_bash_pro)
            tmp.flush()
            remote_file_name = f"/tmp/{os.path.basename(tmp.name)}"
            self.node.scp_file(tmp.name, remote_file_name)
            self.node.run(
                f"mv {remote_file_name} /home/postgres/.bash_profile",
                sudo=True,
            )
            self.node.run(
                "chown postgres:postgres /home/postgres/.bash_profile", sudo=True
            )

    def _create_pg_user(self):
        self.node.run(f"useradd -s /bin/bash postgres", sudo=True)

    def _build_pg(self):
        self.node.run(
            f"""
            {self._clone_repo_cmd('xgres_postgresql', 'postgresql')} &&
            cd /home/postgres/postgresql &&
            git checkout {self.xgres_config.pg_build_tag} &&
            ./configure --prefix={self.database_directory} &&
            make && make install""",
            user="postgres",
            ignore_errors=True,
            sudo=True,
        )

    def _build_xgres(self):
        self.node.run(
            f"""
            {self._clone_repo_cmd('xgres')} &&
            cd /home/postgres/xgres &&
            git checkout {self.xgres_config.build_tag} &&
            make USE_PGXS=1 install""",
            user="postgres",
            ignore_errors=True,
            sudo=True,
        )

    def _pg_ctl_cmd(self, cmd: str) -> str:
        # need to escape postgres env vars so they expand on the remote server
        if cmd == "shutdown" or cmd == "restart":
            return (
                f"{self.database_directory}/bin/pg_ctl {cmd} -m fast -D"
                f" {self.database_directory}/data -l"
                f" {self.database_directory}/{cmd}.log"
            )
        return (
            f"{self.database_directory}/bin/pg_ctl {cmd} -D"
            f" {self.database_directory}/data -l {self.database_directory}/{cmd}.log"
        )

    def _add_custom_settings(self):
        custom_settings_path = f"{self.database_directory}/data/custom.conf"
        with tempfile.NamedTemporaryFile("r+") as tmp:
            tmp.write(self.custom_settings)
            tmp.flush()
            remote_file_name = f"/tmp/{os.path.basename(tmp.name)}"
            self.node.scp_file(tmp.name, remote_file_name)  # local remote
            self.node.run(f"chown postgres:postgres {remote_file_name}", sudo=True)
            self.node.run(
                f"mv {remote_file_name} {custom_settings_path}",
                user="postgres",
                ignore_errors=True,
                sudo=True,
            )
            self.node.run(
                f"cat {self.custom_settings_file} >>"
                f" {self.database_directory}/data/postgresql.conf",
                user="postgres",
                ignore_errors=True,
                sudo=True,
            )

    def _initdb(self):
        self.node.run(
            f"{self._pg_ctl_cmd('initdb')}",
            user="postgres",
            ignore_errors=True,
            sudo=True,
        )

    def _start_pg_server(self):
        self.node.run(
            f"{self._pg_ctl_cmd('start')}",
            user="postgres",
            ignore_errors=True,
            sudo=True,
        )

    def _allow_remote_pg_connections(self):
        pg_hba_rule: str = (
            "host    all             all             0.0.0.0/0              "
            " scram-sha-256"
        )
        append_cmd: str = (
            f"""echo "{pg_hba_rule}" >> {self.database_directory}/data/pg_hba.conf"""
        )
        self.node.run(append_cmd, user="postgres", ignore_errors=True, sudo=True)

    def _setup_benchmark_db(self):
        self.node.run(
            self._local_psql(f"CREATE DATABASE {self.xgres_config.db.database};")
        )

    def _create_extension(self):
        self.psql("CREATE EXTENSION IF NOT EXISTS xgres")

    def _connect_pg_to_xpand(self, bt: BackendTarget):
        # hard coding use_remote_estimate to FALSE until we test other values
        # this has the effect of not sending xpand estimated rows to the pg planner
        all_xpand_hosts = bt.host  #  .split(",")[0]
        self.psql(
            f"""CREATE SERVER {self.public_server_option} FOREIGN DATA WRAPPER xgres OPTIONS (host '{all_xpand_hosts}', port '{bt.port}', dbname '{bt.database}', use_remote_estimate 'FALSE')"""
        )
        self.psql(
            f"""CREATE USER MAPPING FOR PUBLIC SERVER {self.public_server_option} OPTIONS (username '{bt.user}', password '{bt.password}')"""
        )

    def _create_pg_db_user(self):
        """
        setup role for remote pg client connections to use
        """
        self.node.run(
            self._local_psql(
                f"CREATE ROLE {self.xgres_config.db.user} WITH SUPERUSER LOGIN;"
            )
        )
        self.node.run(
            self._local_psql(
                f"ALTER ROLE {self.xgres_config.db.user} ENCRYPTED PASSWORD"
                f" '{self.xgres_config.db.password}';"
            )
        )

    def configure(self):
        """
        build postgres and xgres
        """
        self._create_pg_user()
        self._make_project_directory()
        self._manage_packages("install")
        self._setup_pg_bash_profile()
        self._build_pg()
        self._build_xgres()

    def install(self):
        """
        install and setup postgres with xgres extension
        """
        self._initdb()
        self._allow_remote_pg_connections()
        self._add_custom_settings()
        self._start_pg_server()  # could be self.start()

    def _set_query_path(self):
        if self.xgres_config.xgres_query_path == "FDW":
            query = "SET xgres_fdw.passthrough = false"
        else:
            query = "SET xgres_fdw.passthrough = true"

        self.psql(query)

    def post_install(self, bt: BackendTarget) -> BackendTarget:
        """
        the passed in `bt` is the original backend database targets from `provisioning`
        after being passed in, the proxy becomes the target in `provisioning`

        here we need return our up and running postgres process as the new target
        to `provisioning`

        the returned target will then be used by the driver nodes

        create extension
        create server
        create user mapping
        import foreign schema
        """
        self._setup_benchmark_db()
        self._create_pg_db_user()
        self.pg_client.connect()
        self._create_extension()
        self._connect_pg_to_xpand(bt)
        self._set_query_path()

        return bt

    def db_connect(self):
        try:
            self.pg_client.connect()
            self.pg_client.print_db_version()
        except PgSqlClientException as e:
            raise XgresException(e)

    def self_test(self):
        """
        test connection to the local postgres proxy database
        and also the xpand backend database

        this method doesn't return anything in the abstract definition
        so I am not sure how useful it currently is to a caller
        """
        is_up = self.node.run(
            f"{self._pg_ctl_cmd('status')}",
            user="postgres",
            sudo=True,
            ignore_errors=True,
        )
        if "server is running" in is_up:
            return True
        else:
            return False

    def clean(self):
        """
        stop postgres server and remove install
        """
        self.stop()
        self.node.run(f"rm -rf {self.project_directory}", sudo=True)
        self._manage_packages("erase")

    def start(self, **kwargs):
        # might just use self.node.run here instead of this protected method
        self._start_pg_server()

    def stop(self, **kwargs):
        self.node.run(
            f"{self._pg_ctl_cmd('shutdown')}",
            user="postgres",
            ignore_errors=True,
            sudo=True,
        )
