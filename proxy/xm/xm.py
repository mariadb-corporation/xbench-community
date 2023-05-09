import logging

import yaml
from dacite import from_dict
from typing import List

from compute import BackendTarget, Node, MultiNode
from lib import XbenchConfig

from ..abstract_proxy import AbstractProxy
from .xm_config import XmConfig

XM_CONFIG_FILE = "xm.yaml"

class Xm(AbstractProxy, MultiNode):

    clustered = True

    def __init__(self, nodes: List[Node], **kwargs):
        MultiNode.__init__(self, nodes)

        data=XbenchConfig().get_key_from_yaml(
            yaml_file_name=XM_CONFIG_FILE,
            key_name=self.head_node.vm.klass_config_label,
            use_defaults=True)
        try:
            data.update(kwargs['xm'])
        except: pass

        self.xm_config = from_dict(XmConfig, data=data)
        self.logger.info("xm init")

    def configure(self):
        self.logger.info("xm configure")
        pass

    def install(self):
        self.logger.info(f"xm install(commit={self.xm_config.commit}, mode={self.xm_config.mode})")
        cmake_options='-DBUILD_CONFIG=enterprise'
        if self.xm_config.mode == 'profile':
            self.run_on_all_nodes(
                f"""
sudo dnf install -y perf perl-open
git clone https://github.com/brendangregg/FlameGraph
sudo sh -c 'echo -1 > /proc/sys/kernel/perf_event_paranoid'
sudo sh -c 'echo 0 > /proc/sys/kernel/kptr_restrict'
"""
            , sudo=False)
        if self.xm_config.mode == 'debug':
            cmake_options='-DCMAKE_BUILD_TYPE=Debug'
            self.run_on_all_nodes(
                f"""
sudo dnf install -y gdb python3-pip
sudo pip3 install gdb-tools
echo 'py import duel' > .gdbinit
"""
            , sudo=False)
        self.run_on_all_nodes(
            f"""script -f -c "
set -x
# install prerequisites
sudo dnf install -y git cmake gcc-c++ libaio-devel openssl-devel ncurses-devel bison bash-completion
# git clone
git init bld
cd bld
git fetch --depth 1 https://{self.xm_config.git_token}@github.com/mariadb-corporation/MariaDBEnterprise {self.xm_config.commit}
git checkout FETCH_HEAD
# cmake & make
cmake -DCMAKE_INSTALL_PREFIX=/home/rocky/inst {cmake_options} . -DPLUGIN_CONNECT=NO -DPLUGIN_ROCKSDB=NO -DPLUGIN_SPIDER=NO -DPLUGIN_MROONGA=NO
# make all install
make -j$(( `nproc` + 1)) install
# mysql_install_db
cd /home/rocky/inst
scripts/mariadb-install-db --innodb-log-file-size=1G"
echo 'PATH=$PATH:$HOME/inst/bin' >> .bashrc
"""
        , timeout=3600, sudo=False)
        self.logger.info("xm install done")

    def post_install(self, bt: BackendTarget) -> BackendTarget:
        self.logger.info(f"xm post install(skip={self.xm_config.skip})")
        ips = bt.host.split(',')
        self.run_on_all_nodes(
            f"""
# my.cnf
tee /home/rocky/.my.cnf << __END__
[server]
log-basename=xm
plugin-load-add=ha_xm
plugin-load-add=sql_errlog
plugin-maturity=experimental
xm-remote-host=%(ip)s
xm-remote-port={bt.port}
xm-remote-user={bt.user}
xm-remote-password="{bt.password}"
init-file=/home/rocky/inst/init.sql
enforce-storage-engine=xm
sql-mode=STRICT_TRANS_TABLES,ERROR_FOR_DIVISION_BY_ZERO
__END__
tee /home/rocky/inst/init.sql << __END__
create user if not exists {bt.user}@'%%' identified by "{bt.password}";
grant all privileges on *.* to {bt.user}@'%%';
create database if not exists sysbench;
__END__
"""
        , host_args = [
            {"ip": ips[i % len(ips)]} for i in range(len(self.nodes))
          ]
        , sudo=False)
        self.start()
        if not self.xm_config.skip:
            bt.host = ",".join(self._all_client_ips())
        return bt

    def db_connect(self):
        self.logger.info("xm db connect")
        pass

    def self_test(self):
        self.logger.info("xm self test")
        s = self.run_on_all_nodes("mariadb-admin ping", sudo=False)
        res = True
        for o in s:
            self.logger.info(f"{o.get('hostname')}: {o.get('stdout')}")
            res = res and "is alive" in o.get('stdout')
        return res

    def clean(self):
        self.stop()
        self.logger.info("xm clean")
        self.run_on_all_nodes("rm -rf ~/inst ~/bld ~/.my.cnf", sudo=False)

    def start(self, **kwargs):
        self.logger.info("xm start")
        self.run_on_all_nodes('nohup script -ac "mariadbd-safe &"', sudo=False)

    def stop(self, **kwargs):
        self.logger.info("xm stop")
        self.run_on_all_nodes("pkill mariadbd", sudo=False)
