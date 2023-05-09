import importlib
import logging
import os
from dataclasses import asdict
from typing import Optional, Union

from dacite import from_dict

from cloud import VirtualMachine
from common import backoff, retry, round_down_to_even
from lib.xbench_config import XbenchConfig
from metrics import MetricsServer, MetricsTarget

from .exceptions import NodeException, SshClientException, SshClientTimeoutException
from .os_types import CENTOS7
from .ssh_client import SshClient
from .yum import Yum

DEFAULT_COMMAND_TIMEOUT = 300
DEFAULT_LONG_COMMAND_TIMEOUT = 60 * 60 * 24

# Node exporter
ne_package_name = "golang-github-prometheus-node-exporter"
ne_package_rpm = "golang-github-prometheus-node-exporter-1.2.2-1.el7.x86_64.rpm"
ne_port = 9100


class Node:
    """Represents a single node"""

    # add troubleshooting packages like nmap-ncat and bind-utils
    base_packages = [
        "irqbalance",
        "mdadm",
        "wget",
        "screen",
        "bzip2",
        "vim",
        "lbzip2",
        "chrony",
        "htop",
        "git",
        "sysstat",
        "sshpass",  # For all sorts of ssh atuomation
        "lsof",
    ]

    def __init__(self, vm: VirtualMachine):
        """Init method for Node class. I need a virtual machine and labels from cloud.
        I can extend labels as needed before register in Prometheus

        Args:
            vm (VirtualMachine): Virtual Machine
        """

        self.logger = logging.getLogger(__name__)
        self.vm = vm

        self.xbench_config = XbenchConfig().xbench_config
        self.ms = MetricsServer()  # To be able to register Prometheus exporters

        if self.vm.managed:
            try:
                self.yum = Yum(os_type=self.vm.os_type)
            except NotImplementedError as e:
                raise NodeException(e)
            self.ssh_client = SshClient(
                hostname=self.vm.network.get_public_iface(),
                username=self.vm.ssh_user,
                key_file=self.vm.key_file,
            )

    @classmethod
    def from_dict(cls, params):  # This works as a filter for extra parameters
        v = from_dict(data_class=VirtualMachine, data=params)
        return cls(v)

    def asdict(self):
        return asdict(self.vm)

    @staticmethod
    def _disable_selinux() -> str:
        return "setenforce 0"

    def _disable_network_security(self, really=False) -> str:
        """
        potentially harmful to not use basic network security for
        internet reachable nodes, currently we're assuming we have
        systemctl
        """
        if really:
            self.logger.debug("Disabling network security")
            return f"""
            chkconfig iptables off || true
            systemctl iptables stop || true
            systemctl disable firewalld || true
            systemctl stop firewalld || true
            """
        else:
            return ""

    def _install_base_packages(self) -> str:
        return " ".join([self.yum.install_pkg_cmd()] + Node.base_packages)

    def install_gitv2_for_centos7(self):
        git_v2_repo: str = (
            "https://packages.endpointdev.com/rhel/7/os/x86_64/endpoint-repo.x86_64.rpm"
        )

        self.run(f"{self.yum.remove_pkg_cmd()} git", sudo=True)
        self.run(
            f"{self.yum.install_pkg_cmd()} {git_v2_repo}", sudo=True, ignore_errors=True
        )
        self.run(f"{self.yum.install_pkg_cmd()} git", sudo=True)

    # TODO install and use chrony
    # TODO AWS uses it's own chrony service  https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/set-time.html
    def configure(self, **kwargs):
        """Very basic OS preparation"""

        pem_dir = self.xbench_config.get("pem_dir")

        self.logger.debug("Configuring node OS: basic packages and security set")
        install_epel = self.yum.install_epel_command()

        cmd = f"""
        {install_epel}
        {self._install_base_packages()}
        {self._disable_selinux()}
        {self._disable_network_security(really=self.vm.network.disable_network_security)}
        service chronyd start
        rpm -qa | grep -i epel
        """
        _ = self.run(cmd=cmd, timeout=DEFAULT_COMMAND_TIMEOUT, sudo=True)
        if self.vm.role == "driver" and self.vm.os_type == CENTOS7:
            self.install_gitv2_for_centos7()
        self.set_ssh_passwordless_access(pem_dir)
        self.configure_metrics_exporter()
        self.logger.debug("Node configure done")

    @retry(
        (SshClientException, SshClientTimeoutException),
        NodeException,
        delays=backoff(delay=10, attempts=3),
        max_delay=600,
    )
    def run(
        self,
        cmd: Union[list, str],
        timeout: int = 300,
        sudo=False,
        ignore_errors: bool = False,
        user: str = None,
    ) -> str:
        """This command will retry in case of timeout or command failed

        Args:
            cmd (Union[list, str]): command to run
            timeout (int, optional): timeout in seconds 300.
            sudo (bool, optional): run as root if True. Defaults to False.
            ignore_errors (bool, optional): will give a warning if True, else raise an NodeException. Defaults to False.
            user (str): the user with which to run the `cmd`

        Returns:
            str: output from the command
        """
        return self._unsafe_run(
            cmd=cmd, timeout=timeout, sudo=sudo, ignore_errors=ignore_errors, user=user
        )

    def _unsafe_run(
        self,
        cmd: Union[list, str],
        timeout: int = DEFAULT_LONG_COMMAND_TIMEOUT,
        sudo=False,
        ignore_errors: bool = False,
        user: str = None,
    ) -> str:
        """This is a call for long running tasks such as data generation
        It will not retry! By default it will run for 24 hours!
        """

        output = self.ssh_client.run(
            cmd, timeout=timeout, sudo=sudo, ignore_errors=ignore_errors, user=user
        )
        return output

    def set_ssh_passwordless_access(self, local_dir):
        """Add xbench.pem files to the node"""
        self.prepare_ssh_passwordless_access()
        self.send_pem_files(local_dir)
        self.add_pem_file()
        self.logger.debug("SSH access configured")

    def prepare_ssh_passwordless_access(self):
        cmd = """
        mkdir -p ${HOME}/.ssh
        chmod 700 .ssh
        cat << EOF >>${HOME}/.ssh/config
        Host *
            AddKeysToAgent yes
            StrictHostKeyChecking no
            IdentityFile ~/.ssh/xbench.pem
        EOF
        chmod 600 ${HOME}/.ssh/config
        """
        _ = self.run(cmd=cmd, timeout=DEFAULT_COMMAND_TIMEOUT)

    def send_pem_files(self, local_dir):
        """Send private and public pem files. Add public to the authorized keys"""
        for file in ["xbench.pem", "xbench.pem.pub"]:
            self.ssh_client.send_files(os.path.join(local_dir, file), f".ssh/{file}")

    def add_pem_file(self):
        cmd = """
        cd ~/.ssh/
        cat xbench.pem.pub >>authorized_keys
        """
        _ = self.run(cmd)

    def _configure_metrics_exporter_repo(self):
        if self.yum.version_number() == "7":
            # It seems with 8 package already in epel and it creates issues in GCP
            # RHEL7 repo sometimes times out, let's use RPM saved in xbench repo
            self.ssh_client.send_files(
                f"{XbenchConfig().xbench_home()}/metrics/exporters/{ne_package_rpm}",
                "./",
            )
            cmd = f"{self.yum.install_local_pkg_cmd()} {ne_package_rpm}"
            _ = self.run(cmd, timeout=DEFAULT_COMMAND_TIMEOUT, sudo=True)
        else:
            cmd = f"{self.yum.install_pkg_cmd()} {ne_package_name}"
            _ = self.run(cmd, timeout=DEFAULT_COMMAND_TIMEOUT, sudo=True)

    def _run_metrics_exporter(self):
        cmd = """
        systemctl enable node_exporter
        systemctl start node_exporter
        """
        _ = self.run(cmd, timeout=DEFAULT_COMMAND_TIMEOUT, sudo=True)

    def get_klass(self):

        module_name, klass_name = self.vm.klass.split(".")  # drivers.Sysbench
        module = importlib.import_module(module_name)
        node_klass = getattr(module, klass_name)
        return node_klass

    def get_metrics_interface(self):
        return self.vm.network.get_client_iface()

    def register_metric_target(self, service_name, port):
        mt = MetricsTarget(
            service_name=service_name,
            labels=self.vm.labels(),
            hostname=self.get_metrics_interface(),
            port=port,
        )
        self.ms.register_metric_target(mt)
        self.logger.debug(
            f"{self.vm.name} registered {service_name} exporter on port: {port}"
        )

    def deregister_metric_target(self, service_name, port):
        mt = MetricsTarget(
            service_name=service_name,
            labels=self.vm.labels(),
            hostname=self.get_metrics_interface(),
            port=port,
        )
        self.ms.deregister_metric_target(mt)
        self.logger.debug(
            f"{self.vm.name} de-registered {service_name} exporter on port: {port}"
        )

    def configure_metrics_exporter(self, service_name="node", port=ne_port):
        self._configure_metrics_exporter_repo()
        self._run_metrics_exporter()
        self.register_metric_target(service_name=service_name, port=port)
        self.logger.debug("Metrics exporter configured and running")

    @property
    def os_name(self):
        cmd = "grep ^NAME /etc/os-release"
        output = self.run(cmd=cmd, sudo=True)
        return output.split("=")[1].replace('"', "")

    @property
    def os_version(self):
        cmd = "grep VERSION_ID /etc/os-release"
        output = self.run(cmd=cmd, sudo=True)
        return output.split("=")[1].replace('"', "")

    @property
    def memory_mb(self) -> int:
        """Return total memory in KB"""
        cmd = """
        cat /proc/meminfo | grep MemTotal | awk {"print \$2"}
        """
        return round_down_to_even(int(self.run(cmd)) / 1024)

    @property
    def nproc(self) -> int:
        return int(self.run(cmd="nproc"))

    def send_file(
        self, local_file_name: str, remote_file_name: str, sudo: Optional[bool] = True
    ):
        """This function uses ssh to copy file. Benefits are: you can use sudo!
           scp much better but then you will need to move files around

        Args:
            local_file_name (str): local file. use only small files like certificates
            remote_file_name (str): remote file. Could be anywhere if you use sudo
            sudo (Optional[bool], optional): Defaults to True.
        """
        try:
            with open(local_file_name, "r") as local_file:
                content = local_file.read()

            cmd = f'echo "{content}" > {remote_file_name}'
            self.run(cmd=cmd, sudo=sudo)
        except (FileNotFoundError, IOError) as e:
            raise NodeException(e)

    def scp_file(self, local_file_name: str, remote_file_name: str):
        """
        use SCP to send file instead of SSH -c 'cmd'
        """
        self.ssh_client.send_files(local_file_name, remote_file_name)
