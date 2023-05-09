import tempfile

from common import round_down_to_even
from compute import BackendTarget
from lib import FileTemplate, XbenchConfig

from ..abstract_backend import AbstractBackend
from ..base_backend import SingleManagedBackend
from ..base_pgsql_backend import BasePgSqlBackend
from .pg_config import PGConfig

POSTGRES_CONFIG_FILE = "postgres.yaml"


class PostgreSQLDB(BasePgSqlBackend, SingleManagedBackend,  AbstractBackend):

    def __init__(self, node, **kwargs):

        SingleManagedBackend.__init__(
            self,
            node=node,
            backend_config_yaml_file=POSTGRES_CONFIG_FILE,
            backend_config_klass=PGConfig,
        )
        self.startup_settings = {} # This dict will be passing to template
        BasePgSqlBackend.__init__(self, bt=self.config.db)

    def configure(self):
        """
        TODO:
        sysctl
        hugepages
        shared_buffers and effective_cache_size calculations
        storage setup
        """
        SingleManagedBackend.configure(self)
        self.install_repo()
        self.package_installation()
        # self.add_pg_tools_to_path()
        self.setup_pgdata()
        self.initdb()
        self.allow_remote_connections()
        self.finalize_postgresql_conf()

    def allow_remote_connections(self):
        pg_hba_rule: str = "host    all             all             0.0.0.0/0               scram-sha-256"
        append_cmd: str = (
            f"""echo "{pg_hba_rule}" >> {self.config.data_dir}/pg_hba.conf"""
        )
        self.run(append_cmd, user='postgres')

    def finalize_postgresql_conf(self):
        """Follow this guide
        https://www.enterprisedb.com/postgres-tutorials/comprehensive-guide-how-tune-database-parameters-and-configuration-postgresql

        """
        self.startup_settings["port"] = self.config.db.port
        self.startup_settings["shared_buffers"] = round_down_to_even(self.node.memory_mb/4)
        self.startup_settings["max_connections"] = self.node.nproc*8 + 10
        self.startup_settings["max_connections"] = 256 + self.node.nproc  if self.startup_settings["max_connections"] < 256 else self.startup_settings["max_connections"]

        self.startup_settings["work_mem"] = round_down_to_even(self.startup_settings["shared_buffers"] / self.startup_settings["max_connections"])
        self.startup_settings["effective_cache_size"] = round_down_to_even(self.node.memory_mb*0.75)
        self.startup_settings["max_worker_processes"] = self.node.nproc
        ft: FileTemplate = FileTemplate(filename=self.config.conf_file_template)
        config: str = ft.render(**self.startup_settings)
        local_config_file: tempfile.NamedTemporaryFile = tempfile.NamedTemporaryFile(
            delete=False
        )
        local_config_file.write(str.encode(config))
        local_config_file.close()
        self.node.scp_file(local_config_file.name, f"/tmp/postgresql.conf")
        self.run(
            "mv /tmp/postgresql.conf /data/postgres/postgresql.conf"
        )
        self.run(
            "chown postgres:postgres /data/postgres/postgresql.conf"
        )

    def install(self) -> BackendTarget:
        self.start()
        self.create_database_and_user()
        self.install_and_run_exporter()

        self.db_connect()
        self.print_db_version()
        # BT target is for drivers, so we need to re-adjust how drivers are going to connect
        self.config.db.host = self.node.vm.network.get_client_iface()

        return self.config.db

    def install_repo(self):
        repo_install: str = f"{self.node.yum.install_pkg_cmd()} https://download.postgresql.org/pub/repos/yum/reporpms/EL-{self.yum.version_number()}-x86_64/pgdg-redhat-repo-latest.noarch.rpm"
        self.run(repo_install)

    def package_installation(self):
        # TODO: handle more complex version numbers for specific builds
        # Disable default module
        disable_default_repo = f"{self.yum.disable_module_cmd()} postgresql"
        self.run(disable_default_repo)
        install = f"{self.node.yum.install_pkg_cmd()} postgresql{self.config.version}-server"
        self.run(install)

    # def add_pg_tools_to_path(self):
    #     # TODO: not currently working
    #     # I could do this by writing the .bashrc of the postgres user
    #     export_home: str = (
    #         f"export HOME={self.config.data_dir}"
    #     )
    #     export_pg_bin: str = f"export PATH=/usr/pgsql-{self.config.version}/bin:$PATH"
    #     for cmd in (export_home, export_pg_bin):
    #         self.run(cmd, user='postgres')

    def setup_pgdata(self):
        """ """
        # TODO: handle mounts for cloud storage volumes
        # backend.mariadb.MariaDB.configure for reference implementation
        # to later be factored out into a BaseBackend class
        #
        # I could symbolically link /data/postgres to /var/lib/postgres...
        # I could use a systemctl override file...
        systemd_override_file: str = f"/etc/systemd/system/postgresql-{self.config.version}.service.d/override.conf"
        systemd_override_cmd: str = f'echo "[Service]\nEnvironment=PGDATA={self.config.data_dir}" > {systemd_override_file}'
        create_systemd_override_dir: str = f"mkdir -p /etc/systemd/system/postgresql-{self.config.version}.service.d"
        # Apparently postgres does not like lost+found directory
        make_data_dir: str = f"mkdir -p {self.config.data_dir}; rm -rf {self.config.data_dir}/*"
        set_permissions: str = f"chown -R postgres:postgres {self.config.data_dir}"

        for cmd in (
            make_data_dir,
            set_permissions,
            create_systemd_override_dir,
            systemd_override_cmd,
        ):
            self.run(cmd)

    def initdb(self):
        """
        this must be run as the 'postgres' user account so that the database
        process isn't owned by root
        """
        # TODO: if I could set the $PATH I could use the binary names instead
        initdb_cmd: str = f"/usr/pgsql-{self.config.version}/bin/initdb -D {self.config.data_dir}"
        self.run(initdb_cmd, user='postgres')

    # def self_test(self):
    #     # TODO: create static methods for common string prefixes for running as postgres and using pg_ctl
    #     pg_is_ready: str = f"/usr/pgsql-{self.config.version}/bin/pg_isready"
    #     return self.run(pg_is_ready,user='postgres')

    def clean(self):
        self.stop()
        delete_everything: str = f"rm -rf {self.config.data_dir}"
        self.run(delete_everything)
        self.run(
            f"{self.node.yum.remove_pkg_cmd()} postgresql-{self.config.version}")

    def start(self, **kwargs):
        start_cmd: str = f"systemctl start postgresql-{self.config.version}"
        self.run(start_cmd)

    def stop(self, **kwargs):
        stop_cmd: str = f"systemctl stop postgresql-{self.config.version}"
        self.run(stop_cmd)

    def create_database_and_user(self):
        # we are using the local postgres account
        pgsql_cmd: str = f"""
        CREATE DATABASE {self.config.db.database};
        CREATE ROLE {self.config.db.user} WITH SUPERUSER LOGIN PASSWORD '{self.config.db.password}';
        """
        self.node.run(self.pgsql_cli(pgsql_cmd))  # node.run is required here.

    def install_and_run_exporter(self):
        self.node.ssh_client.send_files(
            f"{XbenchConfig().xbench_home()}/metrics/exporters/postgres_exporter", "./"
        )
        # assumes no SSL for database
        run_exporter: str = f'''DATA_SOURCE_NAME="user=postgres host=/var/run/postgresql/ sslmode=disable" ./postgres_exporter --web.listen-address=':{self.config.prometheus_port}' > ./exporter.log 2>&1 &'''
        self.run(run_exporter)
        self.node.register_metric_target(
            service_name="postgres_exporter", port=self.config.prometheus_port
        )

    def get_logs(self):
        pass
