import json
import logging
from dataclasses import asdict
from typing import List

from compute import Node
from compute.backend_dialect import BackendDialect
from compute.backend_product import BackendProduct
from compute.backend_target import BackendTarget
from xbench.common import get_default_cluster

from ..abstract_backend import AbstractBackend
from ..base_backend import SingleUnManagedBackend
from .alloydb_config import AlloyDBConfig

ALLOYDB_CONFIG_FILE = "alloydb.yaml"


class PgSshSqlClient:
    """Generic class for ssh based psql client. It goes to driver0 and run psql command"""

    clustered = False
    dialect = BackendDialect.pgsql
    product = BackendProduct.postgres

    def __init__(self, **kwargs):  # kwargs are BackendTarget actually
        self.logger = logging.getLogger(__name__)
        self.connect_params = {
            k: v
            for k, v in kwargs.items()
            if k in ["host", "port", "user", "password", "database", "connect_timeout"]
        }
        cluster = get_default_cluster()
        self.driver0 = cluster.get_all_driver_nodes()[0]

    def set_password_for_psql(self):
        cmd = f"""touch ~/.pgpass
        printf "*:*:*:{self.connect_params.get('user')}:{self.connect_params.get('password')}" >> ~/.pgpass
        chmod 0600 ~/.pgpass
        """
        self.driver0.ssh_client.run(cmd)

    def base_command(self) -> str:
        return f"psql -h {self.connect_params.get('host')} -p {self.connect_params.get('port')} -U {self.connect_params.get('user')}"

    def select_one_row(self, q: str):
        """Run query and return json/dict"""
        cmd = f"""{self.base_command()}  {self.connect_params.get('database')} -t -w -c "SELECT json_agg(e) from ({q}) e" """
        r = self.driver0.ssh_client.run(cmd)
        # psql  --username=postgres --host=10.28.1.2 --port=5432 -t   sysbench  -c "SELECT json_agg(e) from (select count(*) from sbtest1) e"
        # TODO catch json.decoder.JSONDecodeError
        return json.loads(r.strip())[0]

    def execute(self, q: str) -> str:
        """Run plain query as it is and return the output"""
        cmd = f'{self.base_command()} -t -w -c "{q}"'
        r = self.driver0.ssh_client.run(cmd)
        return r

    def list_available_databases(self):
        cmd = f"{self.base_command()} -w --list"
        return self.driver0.ssh_client.run(cmd)

    def db_connect(self):
        pass

    def print_non_default_variables(self):
        query = """SELECT name, source, setting, unit FROM pg_settings WHERE source != 'default' AND source != 'override' ORDER by 2, 1 """

        rows = self.execute(query)
        self.logger.info(f"\n{rows}")

    def print_db_size(self, database: str):
        size_query: str = (
            f"SELECT pg_size_pretty(pg_database_size('{database}')) as size"
        )
        row = self.select_one_row(size_query)
        self.logger.info(f"Total Database ({database}) size: \n{row.get('size')}")

    def self_test(self):
        self.print_non_default_variables()


class AlloyDB(SingleUnManagedBackend, PgSshSqlClient, AbstractBackend):
    """Generic class for AlloyDB"""

    clustered = True
    product = "postgres"
    dialect = "pgsql"

    def __init__(
        self,
        nodes: List[Node],  # While this is DBAAS I want to provision read pool replicas
        **kwargs,
    ):
        SingleUnManagedBackend.__init__(
            self,
            node=nodes[0],
            backend_config_yaml_file=ALLOYDB_CONFIG_FILE,
            backend_config_klass=AlloyDBConfig,
        )
        PgSshSqlClient.__init__(self, **asdict(self.config.db))
        host = self.node.vm.network.get_client_iface()
        self.connect_params["host"] = host
        self.host = host

    def connect(self) -> None:
        pass

    # def execute(self, query: str, params: Optional[Iterable[tuple]] = None):
    #     pass

    def configure(self):
        pass

    def create_database(self):
        # AlloyDB doesn't create database by default.
        db_name = self.connect_params.get("database")
        ip = self.connect_params.get("host")
        self.set_password_for_psql()  # We need to do it only once
        r = self.execute(f"CREATE DATABASE {db_name}")
        r = self.list_available_databases()

        if db_name in r:
            self.logger.info(f"AlloyDB database {db_name} created on instance {ip}")
        else:
            self.logger.error(
                f"AlloyDB database {db_name} creation on instance {ip} failed"
            )

    def install(self) -> BackendTarget:
        # BT target is for drivers, so we need to re-adjust how drivers are going to connect
        self.config.db.host = self.host
        self.create_database()
        return self.config.db

    def clean(self):
        pass

    def start(self, **kwargs):
        pass

    def stop(self, **kwargs):
        pass

    def post_data_load(self, database: str):
        pass

    def pre_workload_run(self):
        pass

    def pre_thread_run(self):
        pass

    def get_logs(self):
        pass
