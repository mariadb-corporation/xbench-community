import logging
import os
from typing import Dict

from backend.base_backend import mkdir_command
from benchmark import BenchmarkException
from common.common import get_class_from_klass
from compute import BackendTarget, Node, Yum
from lib import XbenchConfig
from lib.yaml_config import YamlConfig, YamlConfigException

from .abstract_driver import AbstractDriver
from .exceptions import DriverException

DEFAULT_COMMAND_TIMEOUT = 300
DRIVER_CONFIG_FILE = "benchmarks.yaml"
DEFAULT_DIR = "/xbench"  # Where is benchmark will be installed

# ToDo: configure.drivers.sh  --cloud

WORKLOAD_EXPORTER_PORT = 9300
# https://mariadb.com/kb/en/mariadb-package-repository-setup-and-usage/
MARIADB_VERSION = "10.7"


class BaseDriver(AbstractDriver):
    """
    Need to know cloud (to avoid colo)
    need to know OS
    """

    clustered = False

    def __init__(self, node: Node, **kwargs):
        self.node = node
        self.logger = logging.getLogger(__name__)
        self.yum = Yum(os_type=self.node.vm.os_type)

        self.xbench_config = XbenchConfig().xbench_config
        self.xbench_config_dir = self.xbench_config.get("conf_dir")
        self.driver_config_file = DRIVER_CONFIG_FILE

        self.driver_benchmark_list = self.load_config(
            self.node.vm.klass_config_label
        )  # List of benchmarks to install
        self.logger.debug(f"Using {self.driver_benchmark_list} as benchmark list")

    def load_config(self, driver_config_label: str) -> Dict:
        try:
            driver_config_file_name = os.path.join(
                self.xbench_config_dir, self.driver_config_file
            )
            driver_config = YamlConfig(
                yaml_config_file=driver_config_file_name,
            )
            return driver_config.get_key(driver_config_label, use_defaults=True)

        except YamlConfigException as e:
            raise DriverException(e)

    def configure(self):
        """Prepare os to run a driver workload"""
        self.logger.debug("Configuring driver's OS")
        install_epel = self.yum.install_epel_command()
        pm_i = self.yum.install_pkg_cmd()
        pm_r = self.yum.remove_pkg_cmd()
        # sudo yum -y erase mariadb MariaDB-common
        cmd = f"""
        {install_epel} || true
        {pm_i} irqbalance
        sudo systemctl start irqbalance
        sudo systemctl status irqbalance
        # Update open files limits
        echo "* soft nofile 20000" | sudo tee -a /etc/security/limits.conf
        echo "* hard nofile 20000" | sudo tee -a /etc/security/limits.conf
        ulimit -n
        mkdir -p /xbench
        chmod 777 /xbench
         # Git
        {pm_i} git openssl python3
        # Install MariaDB libraries
        {pm_r} MariaDB-client MariaDB-shared
        wget https://downloads.mariadb.com/MariaDB/mariadb_repo_setup
        chmod +x mariadb_repo_setup
        ./mariadb_repo_setup --mariadb-server-version=mariadb-{MARIADB_VERSION} --skip-maxscale --skip-tools
        {pm_i} MariaDB-client MariaDB-shared
        # Installing Postgresql client
        {pm_i} postgresql postgresql-devel
        """
        self.logger.debug("Installing MariaDB/Postgres rpm(s)")
        self.node.run(cmd=cmd, timeout=DEFAULT_COMMAND_TIMEOUT, sudo=True)
        # Mount EBS volume if defined
        if self.node.vm.storage is not None:
            mkdir_command(directory=DEFAULT_DIR, device=self.node.vm.storage.device)
            # TODO instead of 777 try sudo chown $USER
            #  chmod -R 777 {directory}

        # Update environments
        cmd = f"""
        echo 'export XBENCH_HOME={DEFAULT_DIR}' >> ~/.bashrc
        echo 'export PYTHONPATH=$XBENCH_HOME/workload_exporter' >> ~/.bashrc
        """
        stdout = self.node.run(cmd=cmd, timeout=DEFAULT_COMMAND_TIMEOUT)

        self.logger.debug(stdout)
        self.logger.debug("Driver's OS successfully prepared")

    def _setup_pgpass_file(self, bt: BackendTarget):
        """
        hostname:port:database:username:password
        """
        self.node.run("rm -f ~/.pgpass")
        for host in bt.host.split(","):
            self.node.run(
                f"echo '{host}:{bt.port}:*:{bt.user}:{bt.password}' >> ~/.pgpass"
            )
        self.node.run("chmod 0600 ~/.pgpass")

    # Driver doesn't need certificates at least for mysql/mariadb?
    # maybe we could skip this
    def copy_certs(self, bt: BackendTarget):
        """Copy certs from xbench vault to the driver"""

        remove_certs_dir = f"{DEFAULT_DIR}/certs"
        if bt.ssl is not None:
            cmd = f"""
            mkdir -p {remove_certs_dir}
            """
            self.node.run(cmd)

            for _, file in bt.ssl.items():
                self.node.send_file(
                    os.path.expanduser(file),
                    f"{remove_certs_dir}/{os.path.basename(file)}",
                )

    # In the separate project: https://tecadmin.net/setup-autorun-python-script-using-systemd/
    # https://unix.stackexchange.com/questions/236084/how-do-i-create-a-service-for-a-shell-script-so-i-can-start-and-stop-it-like-a-d
    def install(self):
        """Install additional items"""

        self.install_workload_prometheus_exporter()
        self.logger.info("Driver successfully installed")
        try:
            for klass in self.driver_benchmark_list:
                benchmark_klass = get_class_from_klass(klass)
                benchmark_klass(self.node).configure()
                benchmark_klass(self.node).install()
                self.logger.info(f"Benchmark {klass} successfully installed")
        except BenchmarkException as e:
            raise DriverException(e)

    def install_workload_prometheus_exporter(self):
        """
        Workload Prometheus exporter. Uses port 9300 (hardcoded)
        """
        cmd = f"""
        cd {DEFAULT_DIR}
        git clone https://github.com/mariadb-corporation/workload-exporter.git
        cd /xbench/workload-exporter
        pip3 install -r requirements.txt
        cp workload-exporter.service  /lib/systemd/system/
        systemctl enable workload-exporter
        systemctl start workload-exporter
        """
        self.node.run(cmd=cmd, timeout=DEFAULT_COMMAND_TIMEOUT, sudo=True)
        self.node.register_metric_target("workload_exporter", WORKLOAD_EXPORTER_PORT)

    def uninstall_workload_prometheus_exporter(self):
        """Uninstall Prometheus Workload Exporter"""
        cmd = """
        systemctl stop workload-exporter
        systemctl disable workload-exporter
        rm -rf /lib/systemd/system/workload-exporter.service
        pip uninstall -r /xbench/workload-exporter/requirements.txt
        rm -rf /xbench/workload-exporter"""
        self.node.run(cmd=cmd, timeout=DEFAULT_COMMAND_TIMEOUT, sudo=True)
        self.node.deregister_metric_target("workload_exporter", WORKLOAD_EXPORTER_PORT)

    def run_db_script(self, bt: BackendTarget, script: str):
        host = bt.host.split(",")[0]
        cmd: str = ""
        if bt.dialect == "mysql":
            ssl_clause = "--ssl" if bt.ssl is not None else ""
            cmd = (
                f"mysql --user={bt.user} --password='{bt.password}'"
                f" --host={host} --port={bt.port} --connect-timeout=5 {ssl_clause} -e"
                f" '{script}'"
            )
        elif bt.dialect == "pgsql":
            self._setup_pgpass_file(bt)
            cmd = (
                "PGCONNECT_TIMEOUT=5 psql"
                f" --username={bt.user} --host={host} --port={bt.port} postgres"
                f" --command='{script}'"
            )
        self.node.run(cmd)

    def self_test(self, bt: BackendTarget):
        """Run connectivity test

        Args:
            bt (BackendTarget): _description_
        """

        self.copy_certs(bt)
        self.run_db_script(bt, "select 1 as one")
        self.logger.info(f"{self.node.vm.name}: Testing connection passed")

    def clean_database(self, bt: BackendTarget):
        """Clean database"""
        drop_db = f"drop database if exists {bt.database}"
        create_db = f"create database {bt.database}"
        for stmt in (drop_db, create_db):
            self.run_db_script(bt, stmt)

    def clean_packages(self):
        self.logger.debug("Uninstalling MariaDB/Postgres rpm(s)")
        pm_r = self.yum.remove_pkg_cmd()
        cmd = f"""
         # Git Openssl Python3
        {pm_r} git openssl python3
        # Removing MariaDB libraries
        {pm_r} MariaDB-client MariaDB-shared
        # removing Postgresql client
        {pm_r} postgresql
        """
        self.node.run(cmd=cmd, timeout=DEFAULT_COMMAND_TIMEOUT, sudo=True)

    def kill_xbench_procs(self):
        """
        ensure that we find and kill any PIDs that might still be running and holding open files
        on our mounted storage
        """
        self.logger.debug(
            f"Finding and killing any PIDs with open files on {DEFAULT_DIR}"
        )
        pids: str = self.node.run(f"lsof -w -Fp {DEFAULT_DIR}", sudo=True)
        pid_list: list[str] = [p[1:] for p in pids.split("\n")]
        self.node.run(f"kill -9 {' '.join(pid_list)}", sudo=True)

    def clean_storage(self):
        device: str = self.node.vm.storage.device
        directory: str = DEFAULT_DIR
        cmd: str = f"""umount -f {directory}"""
        self.logger.debug(
            f"Unmounting mounted storage at {DEFAULT_DIR} on device {device}"
        )
        self.node.run(cmd=cmd, timeout=DEFAULT_COMMAND_TIMEOUT, sudo=True)

    def clean(self):
        """Uninstall all benchmarks"""
        """MariaDB required libraries"""
        self.clean_packages()
        self.uninstall_workload_prometheus_exporter()
        self.kill_xbench_procs()
        self.clean_storage()
        self.logger.info("Driver successfully uninstalled")
        try:
            for klass in self.driver_benchmark_list:
                benchmark_klass = get_class_from_klass(klass)
                benchmark_klass(self.node).clean()
                self.logger.info(f"Benchmark {klass} successfully uninstalled")
        except BenchmarkException as e:
            raise DriverException(e)
