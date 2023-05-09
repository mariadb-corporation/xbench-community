# -*- coding: utf-8 -*-
# Copyright (C) 2022 dvolkov


# Xpand install guide
# https://docs.clustrix.com/xpand/latest/system-administration-guide/getting-installing-and-upgrading-xpand/xpand-installation-guide-bare-os-instructions/install-xpand/mariadb-xpand-installation-options

import datetime
import json
import os
import os.path
import random
import string
import time
from typing import Dict, List

import requests
import tabulate as tb
from dateutil.parser import parse

from backend.base_backend import MultiManagedBackend, mdadm_command, mkdir_command
from common import backoff_with_jitter, retry, round_down_to_even
from compute import BackendTarget, Node
from compute.exceptions import MultiNodeException
from lib.mysql_client import MySqlClientException

from ..abstract_backend import AbstractBackend
from .base_xpand_backend import BaseXpandBackend
from .exceptions import CheckQuorumException, XpandException
from .xpand_config import XpandConfig

XPAND_CONFIG_FILE = "xpand.yaml"
XPAND_GTM_TIMEOUT = 30  # How long to wait for GTM
XPAND_LOCAL_CACHE_DIR = "/tmp"
CLXNODE = "http://files/pub/clxnode"
XPAND_BASE = "/opt/clustrix"
XPAND_BIN = f"{XPAND_BASE}/bin"
LICENSE_CUTOFF = 24  # License can't be <=24 hrs away from expiration
MAX_REDO_LIMIT_PCT = 10  # MAX_REDO shouldn't be more than 10% of the memory
DEFAULT_LONG_COMMAND_TIMEOUT = 60 * 60 * 24
QPC_LIMIT = 6
STATEMENT_CUTOFF = 60


class Xpand(BaseXpandBackend, MultiManagedBackend, AbstractBackend):
    """Generic class for Xpand"""

    clustered = True

    def __init__(
        self,
        nodes: List[Node],
        **kwargs,
    ):

        self.config: XpandConfig
        MultiManagedBackend.__init__(
            self,
            nodes=nodes,
            backend_config_yaml_file=XPAND_CONFIG_FILE,
            backend_config_klass=XpandConfig,
            **kwargs,
        )

        if self.config.branch == "glassbutte":
            self.conf_file = "/etc/clustrix/clxnode.conf"
        else:  # All branches moving forward
            self.conf_file = "/etc/xpand/xpdnode.conf"

        self.check_license_expiration_date()

        # TODO - bad
        bt_target = self.config.db
        bt_target.host = ",".join(self._all_public_ips())
        BaseXpandBackend.__init__(self, bt_target)

    def check_license_expiration_date(self):
        # Xpand cluster can only be created with valid license, let's make sure
        # the license expiration is at least >24 hrs away
        expiration = self.get_expiration_date_from_license(self.config.license)
        expiration = datetime.datetime.timestamp(expiration)
        diff = datetime.datetime.fromtimestamp(expiration) - datetime.datetime.now()
        diff = diff.total_seconds() / 3600
        self.logger.debug(f"License is {diff} hrs away from expiration")
        if diff <= LICENSE_CUTOFF:
            self.logger.info("License is <=24 hrs away from expiration, please renew!")
            raise XpandException("License is almost expired")

    def configure(self):
        # TODO hugepages
        # yum -y install libhugetlbfs libhugetlbfs-utils
        # Sypported hugepages
        # hugeadm --page-sizes-all
        # Real usage
        # hugeadm --pool-list

        self.logger.info("Running configure on all nodes")
        device = self.head_node.vm.storage.device
        dir = self.config.data_dir

        cmd, device = mdadm_command(self.head_node)
        if cmd is not None:
            self.run_on_all_nodes(cmd)
        if device is not None:
            self.run_on_all_nodes(
                mkdir_command(dir, device, self.mount_storage_to_parent)
            )

        cmd = """
        systemctl start irqbalance
        """
        self.run_on_all_nodes(cmd)
        # Register exporter - I need to do in configure as install run across all environments
        if self.config.enable_prometheus_exporter:
            self.head_node.register_metric_target(
                service_name="xpand", port=self.config.prometheus_port
            )
        if self.head_node.vm.os_type == "RHEL7":
            cmd = """
            yum-config-manager --enable rhel-7-server-rhui-optional-rpms -y
            yum install libdwarf-tools -y
            """
            self.run_on_all_nodes(cmd)

    def install(self) -> BackendTarget:
        """Run actual Xpand install"""
        install_options = (
            self.config.install_options if self.config.install_options else ""
        )
        if self.config.clxnode_mem_pct:
            total_mem = (
                self.head_node.memory_mb
            )  # we're going to assume homogeneous systems
            part_mem = round_down_to_even(total_mem * self.config.clxnode_mem_pct)
            if (
                self.config.max_redo is not None
            ):  #  # I need adjust physical memory for max_redo (value in MB)
                if int(total_mem * MAX_REDO_LIMIT_PCT / 100) < self.config.max_redo:
                    raise XpandException(
                        f"Max_REDO {self.config.max_redo} is to big for total memory"
                        f" {total_mem}"
                    )
                part_mem -= self.config.max_redo

            self.logger.debug(f"Using {part_mem} MB for clxnode-mem")
            # last options in list override previous
            install_options = f"{install_options} --clxnode-mem={part_mem}"

        if self.config.space_allocation_pct:
            dir = self.config.data_dir
            cmd = f"""
            df -B 1073741824  {dir} | tail -n +2 | awk "{{print \$2}}"
            """
            available_space_gb = int(self.run_on_one_node(cmd))
            storage_space_gb = int(
                available_space_gb * self.config.space_allocation_pct
            )
            storage_space_gb = (
                storage_space_gb if storage_space_gb < 15000 else 15000
            )  # ext4 single file limit is 16Tb. Xpand installer max value is 15000
            install_options = f"{install_options} --storage-allocate={storage_space_gb}"
            self.logger.debug(f"Available space is {storage_space_gb}GB")

        # Actual copying the tar
        if self.config.build == "latest":
            build_name = self.get_last_build_file_name()
        else:
            build_name = f"xpand-{self.config.branch}-{self.config.build}.el7"
        if self.config.release:
            build_name = f"xpand-{self.config.release}.el7"
        local_cache_copy = self.download_build(f"{build_name}.tar.bz2")
        self.scp_to_all_nodes(
            local_cache_copy, f"./{os.path.basename(local_cache_copy)}"
        )

        self.logger.info(f"Running xpdnode_install {build_name}")
        install_cmd = f"""
        tar xfj {build_name}.tar.bz2
        ln -s {build_name} xpand-object
        cd xpand-object
        ./xpdnode_install.py --force {install_options} --mysql-port={self.config.db.port} --cluster-addr=%s --management-user={self.head_node.vm.ssh_user} --skip-gui -y
        """

        host_args = [
            {"cmd": install_cmd % (self.nodes[i].vm.network.get_private_iface(),)}
            for i in range(len(self.nodes))
        ]

        self.logger.debug(host_args)
        self.run_on_all_nodes(cmd="%(cmd)s", host_args=host_args, timeout=600)

        self.logger.info(f"Creating database user {self.config.db.user}")
        mysql_cmd = f"""
        create database if not exists {self.config.db.database};
        create user if not exists '{self.config.db.user}'@'%' identified by '{self.config.db.password}';
        grant all privileges on *.* to '{self.config.db.user}'@'%' with grant option;
        flush privileges;
        """
        self.run_on_one_node(self.mysql_cli(mysql_cmd))
        try:
            self.db_connect()
            self.execute(f"set global license='{self.config.license}'")
            self.logger.debug(self.config.license)
            if len(self.nodes) > 1:  # It is possible to have Xpand single zone cluster
                add_ips = ",".join(
                    [
                        f"'{ip}'"
                        for ip in self._all_private_ips()
                        if ip != self.head_node.vm.network.get_private_iface()
                    ]
                )
                self.execute(f"ALTER CLUSTER ADD {add_ips}")
            self.set_globals()
            self.self_test()

        except MySqlClientException as e:
            raise XpandException(e)

        self.stop_statd()
        self.start_prometheus_exporter()  # This call restart service
        # I don't need this if it runs in Prometheus mode
        # self.adjust_statd()

        if self.config.hugetlb is not None:
            self.configure_hugetlb(self.config.hugetlb)

        if self.config.max_redo is not None:
            self.configure_max_redo(self.config.max_redo)

        if self.config.multi_page_alloc is not None:
            self.configure_multi_page_alloc(self.config.multi_page_alloc)

        if self.config.clxnode_additional_args is not None:
            self.configure_clnode_additional_args(self.config.clxnode_additional_args)

        # Chances are that one of the functions above made changes and we have to restart to make it effective
        self.restart()

        time.sleep(XPAND_GTM_TIMEOUT)
        self.db_connect()
        self.set_zones()  # This method will determine if zones are required or not
        self.db_connect()
        self.print_db_version()
        self.set_passwordless_ssh()
        # This is what we are going to save to cluster.yaml so it supposed to be accessible from driver
        self.config.db.host = ",".join(self._all_client_ips())
        self.config.db.dialect = self.dialect
        self.config.db.product = self.product
        return self.config.db

    def set_passwordless_ssh(self, username="xpand"):
        """Implements https://mariadb.com/docs/security/os-user-accounts/xpand/#xpand-system-user-accounts-ssh-configuration"""
        self.logger.info(f"Setting passwordless access for user {username}")
        # Step 1. Enable password authentication
        ssh_cmd = """
        sed -i "s/\PasswordAuthentication no/PasswordAuthentication yes/g" /etc/ssh/sshd_config
        systemctl restart sshd
        """
        self.run_on_all_nodes(ssh_cmd)

        # Step 2. Set random user password
        passwd = "".join(
            random.choices(string.ascii_uppercase + string.ascii_lowercase, k=5)
        )
        pass_cmd = f"""echo "{passwd}" | sudo passwd {username} --stdin"""
        self.run_on_all_nodes(pass_cmd)

        # Step 3. Generate the rsa key
        rsa_cmd = f"""sudo -i -u {username}  -S $SHELL -c 'if [[ ! -f ~/.ssh/id_rsa ]] ; then echo "Y" | ssh-keygen -t rsa -f ~/.ssh/id_rsa -P "" ; fi'"""
        self.run_on_all_nodes(rsa_cmd, sudo=False, ignore_errors=True)

        # Step 4. Send the keys
        for node in self.nodes:  # ech node
            for node_ in self.nodes:  # send it's own rsa to all others
                send_cmd = f"""sshpass -p {passwd} ssh-copy-id -o "StrictHostKeyChecking=no" {username}@{node_.vm.network.get_client_iface()}"""
                node.run(send_cmd, sudo=True, user=username, ignore_errors=True)

    @staticmethod
    def zone_unique_str(n: Node):
        return f"{n.vm.env}{n.vm.zone}"

    def set_zones(self):
        """https://jira.mariadb.org/browse/PERF-216
        If we have more then 3 zones then we should properly set Zone attribute.
        Unique zone is a combination of the env and zone property of node/virtual machine
        """
        xpand_zones: Dict[str, int] = {}
        xpand_zone_id = 1
        # First let's see how many zone do we have
        for n in self.nodes:
            zone_unique_str = self.zone_unique_str(n)
            if xpand_zones.get(f"{zone_unique_str}", None) is None:
                xpand_zones[zone_unique_str] = xpand_zone_id
                xpand_zone_id += 1

        self.logger.debug(f"Zone dict: {xpand_zones}")

        if len(xpand_zones) > 1:
            for n in self.nodes:
                nodeid = self.get_nodeid_by_ip(n.vm.network.get_private_iface())
                zone = xpand_zones.get(self.zone_unique_str(n))
                query = f"ALTER CLUSTER {nodeid} ZONE {zone}"
                self.execute(query)

            self.execute("alter cluster reform")
            self.logger.info(f"Zone information:\n{tb.tabulate(self.get_zone_info())}")

    def get_zone_info(self) -> Dict:

        query = "select nodeid, be_ip, zone from system.nodeinfo"
        return self.select_all_rows(query)

    def get_nodeid_by_ip(self, ip: str):
        """Return nodeid by be_ip"""
        zone_info = self.get_zone_info()
        for n in zone_info:
            if n.get("be_ip") == ip:
                return n.get("nodeid")

        raise XpandException(f"Node with {ip} was not found in the cluster")

    # TODO This should be done after install and before start
    def stop_statd(self):
        # /opt/clustrix/bin/clx nanny stop_job statd # temporary
        cmd = f"""{XPAND_BIN}/clx nanny stop_job statd
        cat {XPAND_BASE}/etc/nanny.conf | grep -v stat > {XPAND_BASE}/etc/nanny.conf.new
        mv {XPAND_BASE}/etc/nanny.conf.new {XPAND_BASE}/etc/nanny.conf
        """
        self.run_on_all_nodes(cmd=cmd)

    def start_prometheus_exporter(self):
        # check /etc/clustrix/clxnode.conf and how /opt/clustrix/bin/nanny.sh uses it
        # sudo -u xpand /opt/clustrix/bin/statd.py -e --prometheus --prometheus-port 9200
        # To make it permanent we need to change: /opt/clustrix/etc/nanny.conf
        if self.config.enable_prometheus_exporter:
            cmd = f"""
            echo "add_job statp -c \\"{XPAND_BIN}/statd.py -e --prometheus --prometheus-port {self.config.prometheus_port}\\"" >> {XPAND_BASE}/etc/nanny.conf
            systemctl restart clustrix
            """
            self.run_on_all_nodes(cmd)
            time.sleep(XPAND_GTM_TIMEOUT)
            self.logger.info(
                "Started xpand prometheus exporter on all nodes port:"
                f" {self.config.prometheus_port}"
            )
            # Register call already has happened in configure

    def set_globals(self):
        """Set global variables for the instance"""
        self.logger.info("Setting global variables")
        hash_dist_min_slices_adjusted = False
        for k, v in self.config.globals.items():
            self.execute(f"set global {k} = {v}")
            hash_dist_min_slices_adjusted = (
                True if k == "hash_dist_min_slices" else hash_dist_min_slices_adjusted
            )

        if not hash_dist_min_slices_adjusted:
            # adjust hash_dist_min_slices
            nproc = self.head_node.nproc
            num_slices = nproc * self.num_nodes - self.num_nodes
            self.execute(f"set global hash_dist_min_slices = {num_slices}")

    # Probably I don't need it a we run statd in Prometheus mode which is read only
    def adjust_statd(self):
        num_nodes = len(self.nodes)
        mysql_cmd = f"""
        alter table clustrix_statd.hotness_history slices = {num_nodes} replicas = 2 container = layered, primary key distribute = 5, index timestamp_2 distribute = 2, index timestamp distribute = 2;
        alter table clustrix_statd.qpc_current     slices = {num_nodes} replicas = 1 container = layered, primary key distribute = 1, index rank distribute = 2;
        alter table clustrix_statd.qpc_history     slices = {num_nodes} replicas = 2 container = layered, primary key distribute = 3, index timestamp distribute = 3, index is_rollup distribute = 3;
        alter table clustrix_statd.statd_config    replicas = ALLNODES container = layered;
        alter table clustrix_statd.statd_current   slices = {num_nodes*4}  replicas = 1 container = layered, primary key distribute = 1;
        alter table clustrix_statd.statd_history   slices = {num_nodes*4}  replicas = 2 container = layered, primary key distribute = 2, add index timestamp_cover (timestamp,id,value) distribute = 2, drop index timestamp;
        alter table clustrix_statd.statd_metadata  replicas = ALLNODES container = layered;
        """
        self.run_on_one_node(self.mysql_cli(mysql_cmd))

    # @staticmethod
    # def mysql_cli(cmd):
    #     """Simplify running multiply command via mysql command line"""
    #     return f"""mysql -A -s << EOF
    #     {cmd.replace("'", '"')}
    #     EOF
    #     """

    # TODO: this is duplicated in Driver.BaseDriver.kill_backend_procs
    def kill_backend_procs(self):
        """
        ensure that we find and kill any PIDs that might still be running and holding open files
        on our mounted storage
        """
        self.logger.debug(
            f"Finding and killing any PIDs with open files on {self.config.data_dir}"
        )
        for node in self.nodes:
            pids: str = node.run(f"lsof -w -Fp {self.config.data_dir}", sudo=True)
            pid_list: list[str] = [p[1:] for p in pids.split("\n")]
            node.run(f"kill -9 {' '.join(pid_list)}", sudo=True)

    def clean(self):
        self.logger.info("Running Xpand un-install")
        self.stop()
        self.kill_backend_procs()
        clean_cmd = """
        rm -rf /data/clustrix/*
        umount --force /data/clustrix
        rm -rf /opt/clustrix
        rm -rf /etc/clustrix
        rm -rf /etc/xpand
        rm -f xpand-object
        rpm -ev --nodeps $(rpm -qa | grep xpand) || true
        rpm -ev --nodeps $(rpm -qa | grep xpand-utils) || true
        rpm -ev --nodeps $(rpm -qa | grep xpand-common) || true
        rm -f /dev/shm/*
        echo 0 | sudo tee /proc/sys/vm/nr_hugepages
        """
        self.run_on_all_nodes(clean_cmd)

    @retry(
        (CheckQuorumException, MultiNodeException),
        XpandException,
        delays=backoff_with_jitter(delay=5, attempts=15, cap=15),
    )
    def self_test(self):
        # This is a main test
        self.check_quorum()
        self.check_license_expiration_date()
        self.print_non_default_variables()
        # But I need to make sure clx get it in all nodes
        try:
            cmd = f"{XPAND_BIN}/clx s"
            self.run_on_all_nodes(cmd)
            self.logger.info("clx status OK")
        except XpandException as e:
            raise CheckQuorumException(e)

    # def db_connect(self):
    #     """Connect to Xpand"""
    #     try:
    #         self.connect()
    #     except MySqlClientException as e:
    #         raise XpandException(e)

    def start(self):
        cmd = f"""
        systemctl start clustrix
        systemctl start hugetlb
        """
        self.logger.debug("Running start command in all nodes")
        self.run_on_all_nodes(cmd)

    def stop(self):
        cmd = f"""
        systemctl stop clustrix || true
        systemctl stop hugetlb || true
        """
        self.logger.debug("Running stop command on all nodes")
        self.run_on_all_nodes(cmd)

    def restart(self):
        self.stop()
        self.start()

    def check_logs(self):
        """Grep logs for any errors
        Return: an Exception if FATAL error found
        """
        # Do we always have a log in this directory? I think there is clx command to do grep over multiple logs.
        # I need always return true to prevent get an exception that command failed. grep return 1 if not found
        cmd = "grep FATAL  /data/clustrix/log/clustrix.log || true"
        ret_dict = self.run_on_all_nodes(cmd)
        for k, v in ret_dict.items():
            output = "".join(v[0].split())
            if output:
                raise XpandException(f"Fatal errors found on {k} node")

    def check_quorum(self):
        """Check if we have a quorum"""
        # This is for latest mainline1.
        query = "SELECT nid, status FROM system.membership where status = 'quorum'"
        try:
            rows = self.select_all_rows(query)
            self.logger.debug(f"Quorum info: {rows}")
            if len(rows) == len(self.nodes):
                self.logger.info("Cluster is in quorum")
            else:
                self.execute("alter cluster reform")  # attempt to reform the cluster
                raise CheckQuorumException(
                    "There is no quorum in the cluster or cluster was not formed"
                    " properly"
                )
        except MySqlClientException as e:
            raise CheckQuorumException("Unable to check quorum")

    def get_expiration_date_from_license(self, license: str) -> datetime.date:
        """Return license expiration date"""

        license_info_as_dict = json.loads(license)
        return parse(license_info_as_dict.get("expiration"), ignoretz=True)

    @retry(
        requests.exceptions.ConnectionError,
        XpandException,
        delays=backoff_with_jitter(delay=3, attempts=10, cap=10),
    )
    def get_last_build_file_name(self) -> str:
        """Internal method to get latest build

        Args:
            branch (str, optional): _description_. Defaults to None.

        Returns:
            str: full path to the clx object
        """
        url = f"{CLXNODE}/{self.config.branch}/LATEST.el7"
        self.logger.debug(url)
        r = requests.get(url)
        if r.status_code == 200:
            latest_build = r.text.strip("\n")
            self.logger.info(f"Found {latest_build} as the latest build in clxnode")
            return f"{latest_build}"  # .tar.bz2
        else:
            raise XpandException("Cannot find the latest build, access error?")

    @retry(
        requests.exceptions.ConnectionError,
        XpandException,
        delays=backoff_with_jitter(delay=3, attempts=10, cap=10),
    )
    def download_build(self, build_file_name: str) -> str:
        """Internal method to download locally from clxnode

        Args:
            path (str): _description_

        Returns:
            str: _description_
        """

        local_cache_file = f"{XPAND_LOCAL_CACHE_DIR}/{build_file_name}"
        os.path.exists(local_cache_file)
        if os.path.exists(local_cache_file):
            self.logger.info(f"{build_file_name} found in the local cache")
        else:
            url = f"{CLXNODE}/{self.config.branch}/{build_file_name}"
            r = requests.get(url, stream=True)

            if r.status_code != 200:
                raise XpandException(f"Cannot access {url}")

            with open(local_cache_file, "wb") as clxobject:
                for chunk in r.iter_content(chunk_size=1024):
                    if chunk:
                        clxobject.write(chunk)
            # TODO check file integrity
            self.logger.info(f"{build_file_name} successfully downloaded ")

        return local_cache_file

    def configure_multi_page_alloc(self, page_size: int):
        cmd = f"echo MULTIPAGE_ALLOC={page_size}G >> {self.conf_file}"
        self.run_on_all_nodes(cmd)

    def configure_clnode_additional_args(self, clxnode_args: str):
        cmd = f"echo CLXNODE_ADDITIONAL_ARGS='{clxnode_args}' >> {self.conf_file}"
        self.run_on_all_nodes(cmd)

    def configure_hugetlb(self, enable: bool):
        if enable:
            self.logger.debug("Enabling hugetlb...")
            sed_cmd = f"""
            sed -i 's/#HUGE_TLB_ENABLE/HUGE_TLB_ENABLE/' {self.conf_file}
            """
            self.run_on_all_nodes(sed_cmd)
        else:
            self.logger.debug("Disabling hugetlb...")
            sed_cmd = f"""
            sed -i 's/HUGE_TLB_ENABLE/#HUGE_TLB_ENABLE/' {self.conf_file}
            """
            self.run_on_all_nodes(sed_cmd)

    def configure_max_redo(self, max_redo: int):
        self.logger.debug("Configuring max_redo...")
        # Only need to fix clxnode.sh for glassbutte branch (Bug 34929)
        if self.config.branch == "glassbutte":
            self.logger.debug("Fixing clxnode.sh for glassbutte")
            fix_cmd = """
            sed -i "s/FLAG_REDO=false && MAX_REDO=\\"128\\" #MB/\{ FLAG_REDO=false; MAX_REDO=\\"128\\"; \} #MB/g" /opt/clustrix/bin/clxnode.sh
            """
            self.run_on_all_nodes(fix_cmd)
        sed_cmd = f"""
        sed -i 's/#MAX_REDO=128/MAX_REDO={max_redo}/g' {self.conf_file}
        """
        self.run_on_all_nodes(sed_cmd)

    def post_data_load(self, database: str):
        """This function is called after data load complete
        Run re-balancer and disable it right after
        """
        self.logger.info("Running post load tasks")
        self.db_connect()
        mysql_cmd = """
        set GLOBAL rebalancer_optional_tasks_enabled = True;
        CALL system.task_run('rebalancer_gather');
        CALL system.task_run('rebalancer_redistribute');
        CALL system.rebalancer_flush();

        CALL system.task_run('rebalancer_gather');
        CALL system.task_run('rebalancer_split');
        CALL system.rebalancer_flush();

        CALL system.task_run('rebalancer_gather');
        CALL system.task_run('rebalancer_rebalance');
        CALL system.rebalancer_flush();

        CALL system.task_run('rebalancer_gather');
        CALL system.task_run('rebalancer_rebalance_distribution');
        CALL system.rebalancer_flush();

        CALL system.task_run('rebalancer_gather');
        CALL system.task_run('rebalancer_rerank');
        CALL system.rebalancer_flush();

        CALL system.task_run('rebalancer_gather');
        CALL system.task_run('rebalancer_rerank_distribution');
        CALL system.rebalancer_flush();
        """
        # TODO
        self.run_on_one_node(self.mysql_cli(mysql_cmd))

        # Wait until rebalancer activity done
        query = "select * from system.rebalancer_activity_log WHERE finished IS NULL"
        self.wait_until_no_data(query)

        mysql_cmd = """
        set GLOBAL rebalancer_optional_tasks_enabled = False;
        """
        # TODO
        self.run_on_one_node(self.mysql_cli(mysql_cmd))
        # self.analyze_all_tables(database)

    def do_layer_merging(self):
        """This runs before each thread starts
        How it works: http://wiki/index.php/Inspecting_layered_trees
        See all variables here: https://docs.clustrix.com/display/SAG75/Global+Variables
        """
        self.logger.info("Running layer_merging")
        self.db_connect()

        # TODO Get current valued and then restore them
        # Enable fast layer merging activity
        # set global layer_merge_always_full=true;

        mysql_cmd = """
        set global layer_short_age_secs=60;
        set global layer_max_merge_per_device=10;
        set global layer_max_merge_scheduled_per_device=10;
        set global layer_max_top_layer_size_bytes=67108864;
        set global layer_copy_speed_bytes=10485760;
        set global layer_copy_speed_rows=2000000;
        set global layer_short_read=200;
        """
        self.run_on_one_node(self.mysql_cli(mysql_cmd))

        # Wait until this query return no rows
        query = (
            "select * from system.layer_merges where finished is null and state !="
            " 'Cancelled'"
        )
        self.wait_until_no_data(query)

        # Enable Optimal layer merging activity
        mysql_cmd = """
        set global layer_short_age_secs=default;
        set global layer_max_merge_per_device=default;
        set global layer_max_merge_scheduled_per_device=default;
        set global layer_merge_always_full=default;
        set global layer_max_top_layer_size_bytes=default;
        set global layer_copy_speed_bytes=default;
        set global layer_copy_speed_rows=default;
        set global layer_short_read=default;
        """
        self.run_on_one_node(self.mysql_cli(mysql_cmd))

    def backup(self, database: str, dest: str, cloud_args: dict, target: str):
        cmd = f"set global backup_backup_concurrency = {self.head_node.nproc}"
        self.run_on_one_node(self.mysql_cli(cmd))
        if target == "ftp":
            server_ip = cloud_args["ftp_server"]["hostname"]
            user = cloud_args["ftp_server"]["username"]
            password = cloud_args["ftp_server"]["password"]
            root_folder = cloud_args["ftp_server"]["root_folder"]
            backup_cmd = f"""backup {database} to 'ftp://{user}:{password}@{server_ip}/{root_folder}/{dest}'"""
        elif target == "s3":
            bucket = cloud_args["s3"]["bucket"]
            key_id = cloud_args["aws_access_key_id"]
            secret_key = cloud_args["aws_secret_access_key"]
            region = cloud_args["aws_region"]
            backup_cmd = f"""backup {database} to \'s3://{bucket}/{dest}?access_key_id={key_id}&secret_access_key={secret_key}&region={region}\'"""
        else:
            raise XpandException(f"Unsupported backup target: {target}")
        # TODO: For some reason this doesn't work, but it should
        # self.db_connect()
        # self.execute(backup_cmd)
        self.run_on_one_node(
            self.mysql_cli(backup_cmd), timeout=DEFAULT_LONG_COMMAND_TIMEOUT
        )

    def restore(self, database: str, src: str, cloud_args: dict, target: str):
        cmd = f"drop database if exists {database};"
        self.run_on_one_node(self.mysql_cli(cmd))
        cmd = f"set global backup_restore_concurrency = {self.head_node.nproc}"
        self.run_on_one_node(self.mysql_cli(cmd))
        if target == "ftp":
            server_ip = cloud_args["ftp_server"]["hostname"]
            user = cloud_args["ftp_server"]["username"]
            password = cloud_args["ftp_server"]["password"]
            root_folder = cloud_args["ftp_server"]["root_folder"]
            backup_cmd = f"""
            restore {database} from 'ftp://{user}:{password}@{server_ip}/{root_folder}/{src}'"""
        elif target == "s3":
            bucket = cloud_args["s3"]["bucket"]
            key_id = cloud_args["aws_access_key_id"]
            secret_key = cloud_args["aws_secret_access_key"]
            region = cloud_args["aws_region"]
            backup_cmd = (
                f"restore {database} from"
                f" 's3://{bucket}/{src}?access_key_id={key_id}&secret_access_key={secret_key}&region={region}'"
            )
        else:
            raise XpandException(f"Unsupported restore target: {target}")
        # TODO: For some reason this doesn't work, but it should
        # self.db_connect()
        # self.execute(backup_cmd)
        self.run_on_one_node(
            self.mysql_cli(backup_cmd), timeout=DEFAULT_LONG_COMMAND_TIMEOUT
        )

    def get_logs(self) -> str:
        """
        this uses clx logdump https://mariadb.com/docs/ent/ref/xpand/cli/clx/#logdump
        the `-s 24` arguments means '24 hours from right now' so that we pick up all
        logs created in the last 24 hours
        """
        logdump_cmd: str = f"{XPAND_BIN}/clx -i ~/.ssh/xbench.pem -s 24 logdump query"
        return self.run_on_one_node(logdump_cmd, sudo=False)

    def flush_qpc(self):
        self.logger.info("Flushing QPC on all nodes")
        cmd = """mysql system -e "call qpc_flush()" """
        self.run_on_all_nodes(cmd=cmd)

    def qpc_queries(self, output_dir):
        """Gather longest running queries from QPC and save explain statements.

        Args:
            str: Artifact directory to save qpc_queries.txt and query_explains.txt
        Returns:

        """
        qpc_query = f"""
        SELECT
            statement,
            left(replace(replace(replace(statement,'\n',' '), '   ', ' '), '  ', ' '), {STATEMENT_CUTOFF}) as stmnt,
            sum(exec_count) as s_exec_count,
            avg(avg_latency_ms) as avg_lat_ms,
            sum(cpu_runtime_ns)/1000/1000 as s_cpu_runtime_ms,
            sum(cpu_waittime_ns)/1000/1000 as s_cpu_waittime_ms,
            sum(fc_waittime_ns)/1000/1000 as s_fc_waittime_ms,
            sum(bm_waittime_ns)/1000/1000 as s_bm_waittime_ms,
            sum(lockman_waittime_ms) as s_lockman_waittime_ms,
            sum(trxstate_waittime_ms) as s_trxstate_waittime_ms,
            sum(bm_perm_waittime_ms) as s_bm_perm_waittime_ms,
            sum(wal_perm_waittime_ms) as s_wal_perm_waittime_ms,
            sum(forwards) as s_fowards,
            sum(broadcasts) as s_broadcasts,
            sum(fragment_executions) as s_fragment_executions,
            sum(barrier_forwards) as s_barrier_forwards
        FROM
            system.qpc_queries
        WHERE
            flushed = 0
            AND database = '{self.config.db.database}'
        GROUP BY
            stmnt
        ORDER BY
            avg_lat_ms desc LIMIT {QPC_LIMIT};
        """
        self.db_connect()
        rows = self.select_all_rows(qpc_query)
        qpc_output = ""
        explains_output = ""
        if len(rows) > 0:
            for k in rows[0].keys():
                if k != "statement":  # We don't need statement field
                    qpc_output = f"{qpc_output}{k}\t"
            qpc_output = f"{qpc_output}\n"
            for row in rows:
                row["statement"] = " ".join(row["statement"].split())
                cmd = f"EXPLAIN {row['statement']}"
                try:
                    rows = self.select_all_rows(cmd)
                except MySqlClientException:
                    self.logger.warning(f"Invalid SQL: {cmd}")
                    rows = []
                tb.PRESERVE_WHITESPACE = True
                explain = tb.tabulate(
                    rows, headers="keys", numalign="right", tablefmt="presto"
                )
                explains_output = (
                    f"{explains_output}--------------\nstatement ="
                    f" {row['statement']}\n--------------\n{explain}\n\n\n"
                )
                for i, v in enumerate(row.values()):
                    if i > 0:  # We don't need to print entire statement
                        qpc_output = f"{qpc_output}{v}\t"
                qpc_output = f"{qpc_output}\n"

        qpc_queries_file: str = os.path.join(output_dir, "qpc_queries.txt")
        self.logger.debug(f"Saving QPC queries to {qpc_queries_file}")
        with open(qpc_queries_file, "w") as qpc_queries:
            qpc_queries.write(qpc_output)
        explain_queries_file: str = os.path.join(output_dir, "explain_queries.txt")
        self.logger.debug(f"Saving QPC queries to {explain_queries_file}")
        with open(explain_queries_file, "w") as explain_queries:
            explain_queries.write(explains_output)

    def pre_workload_run(self, **kwargs):
        super().pre_workload_run()
        self.flush_qpc()

    def post_workload_run(self, **kwargs):
        super().post_workload_run()
        self.qpc_queries(kwargs.get("output_dir"))
