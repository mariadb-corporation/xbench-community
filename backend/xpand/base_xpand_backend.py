# -*- coding: utf-8 -*-
# Copyright (C) 2022 dvolkov

import time

from tabulate import tabulate

from compute.backend_dialect import BackendDialect
from compute.backend_product import BackendProduct
from compute.backend_target import BackendTarget

from ..base_mysql_backend import BaseMySqlBackend


class BaseXpandBackend(BaseMySqlBackend):
    """Generic class for MySQL compatible backends"""

    product = BackendProduct.xpand
    dialect = BackendDialect.mysql

    def __init__(self, bt: BackendTarget):
        BaseMySqlBackend.__init__(self, bt)

    def print_non_default_variables(self):
        query = """
        SELECT name, value, default_value
        FROM system.global_variables
        JOIN system.global_variable_definitions USING (name)
        WHERE value != default_value
        AND name NOT IN ('cluster_id', 'cluster_name', 'clustrix_version', 'customer_name', 'format_version',
        'global_variables_ignored_version', 'license', 'mysql_port', 'server_id', 'server_uuid',
        'ssl_cert', 'ssl_key', 'view_strmaps_upgraded')
        """
        rows = self.select_all_rows(query)
        self.logger.info(f"\n{tabulate(rows)}")

    def print_db_size(self, database: str) -> None:
        """Print database size

        Args:
            database (str): database name
        """
        query = (
            "select sum(bytes)/1000000000 as db_size from system.container_stats cs"
            " join system.table_replicas tr on cs.replica = tr.replica where database"
            f" = '{database}'"
        )
        row = self.select_one_row(query)
        self.logger.info(
            f"Total Database ({database}) size: \n{row.get('db_size')} (GB) "
        )

    def analyze_all_tables(self, database: str):
        """Analyze all tables for given database

        Args:
            database (str): database name
        """
        self.db_connect()
        self.logger.info("Running analyze for all tables")
        query = (
            "select rel.name as table_name FROM system.databases db JOIN"
            " system.relations rel ON db.db = rel.db JOIN system.representations rep"
            f" ON rel.table = rep.relation where db.name = '{database}'"
        )
        r = self.select_all_rows(query)
        # For table_name in
        for t in r:
            table_name = t.get("table_name")
            query = f"analyze full table {database}.{table_name}"
            self.execute(query)

    def pre_workload_run(self, **kwargs):
        # self.do_layer_merging()
        pass

    def post_workload_run(self, **kwargs):
        pass

    def pre_thread_run(self, **kwargs):
        # self.do_layer_merging()
        pass

    def wait_until_no_data(self, query: str):
        """Wait until query returns no rows

        Args:
            query (str): _description_
        """
        while True:
            r = self.select_one_row(query)
            if len(r) > 0:
                time.sleep(5)
            else:
                break
