# -*- coding: utf-8 -*-
# Copyright (C) 2023 dvolkov


import os
import time
from subprocess import Popen

from .exceptions import XbenchException
from .xbench import Xbench


class xCommands(Xbench):
    """Main class to execute external commands"""

    def __init__(
        self,
        cluster_name,
    ):
        super(xCommands, self).__init__(cluster_name)
        self.cluster = self.load_cluster()
        cluster_config_yaml = os.path.join(
            self.clusters_dir, f"{self.cluster_name}.yaml"
        )
        self.logger.info(f"Cluster file is {cluster_config_yaml}")

    def ls(self):
        print(f"state: {self.cluster.state}")
        self.cluster.render_cluster_tree()
        for m, n in self.cluster.members.items():
            print(f"{m}:{n.vm.network.public_ip},{n.vm.network.private_ip}")
        print(
            f"bt:{self.cluster.bt.dialect}:{self.cluster.bt.user}:{self.cluster.bt.password}:{self.cluster.bt.host}:{self.cluster.bt.port}:{self.cluster.bt.database}"
        )

    # TODO Check if RunSubprocess can be used. It has a lot of pre-built logic already.
    def run(self, command):
        proc = Popen(command, shell=True)
        while proc.poll() is None:  # sub-process not terminated
            time.sleep(0.1)

        if proc.returncode != 0:
            raise XbenchException(
                f"Command {command} failed with error code {proc.returncode}"
            )

    def ssh(self, member: str, ssh_command: list[str]):
        """Run ssh command on member of the cluster.

        Args:
            member (str): member of the cluster, driver-0, backend1-0 etc
            ssh_command (list[str]): python convert into the list all commands which contain space

        Raises:
            XbenchException: If member doesn't exists
        """
        n = self.get_member(member)

        base_ssh_command = (
            "ssh -o StrictHostKeyChecking=no -o LogLevel=ERROR  -i"
            f" {n.vm.key_file} {n.vm.ssh_user}@{n.vm.network.public_ip}"
        )
        command = (
            f"{base_ssh_command} -T {' '.join(ssh_command)}"  # -T to allocate pseudo tty
            if ssh_command
            else base_ssh_command
        )
        self.run(command)

    def get_member(self, member):
        n = self.cluster.members.get(member, None)
        if n is None:
            raise XbenchException(
                f"Member {member} does not exist. Use 'ls' command to see all valid"
                " members of the cluster."
            )

        return n

    # TODO allow override bt properties form command line
    def sql(self, member: str, sql_command: list[str]):
        """Run mariadb or psql locally"""

        n = self.get_member(member)

        if self.cluster.bt.dialect == "mysql":
            base_cmd = (
                "mariadb -A -u"
                f" {self.cluster.bt.user} --password={self.cluster.bt.password} --port"
                f" {self.cluster.bt.port} --host={n.vm.network.public_ip} --database={self.cluster.bt.database}"
            )
            command = (
                f"""{base_cmd} -e "{' '.join(sql_command)}" """
                if sql_command
                else base_cmd
            )
            self.run(command)
        elif self.cluster.bt.dialect == "pgsql":
            base_cmd = (
                f"PGPASSWORD={self.cluster.bt.password} psql -U"
                f" {self.cluster.bt.user} -d {self.cluster.bt.database} -h"
                f" {n.vm.network.public_ip} -w"
            )
            command = (
                f"""echo "{' '.join(sql_command)}" | {base_cmd}  """
                if sql_command
                else base_cmd
            )
            self.run(command)

        else:
            raise XbenchException("not supported dialect")

    def send(self, member: str, local_file: str, remote_file: str):
        """Send local file to the cluster member

        Args:
            member (str): cluster member
            local_file (str): local file
            remote_file (str): remote file
        """

        if not os.path.exists(local_file):
            raise XbenchException(f"File {local_file} does not exist")

        n = self.get_member(member)
        scp_command = (
            "scp -r -o StrictHostKeyChecking=no -i"
            f" {n.vm.key_file} {local_file} {n.vm.ssh_user}@{n.vm.network.public_ip}:{remote_file}"
        )
        self.run(scp_command)

    def recv(self, member: str, remote_file: str, local_file: str):
        """Send local file to the cluster member

        Args:
            member (str): cluster member
            local_file (str): local file
            remote_file (str): remote file
        """

        n = self.get_member(member)
        scp_command = (
            "scp -r -o StrictHostKeyChecking=no -i"
            f" {n.vm.key_file} {n.vm.ssh_user}@{n.vm.network.public_ip}:{remote_file} "
            f" {local_file}"
        )
        self.run(scp_command)
