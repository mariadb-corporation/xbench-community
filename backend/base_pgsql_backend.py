# -*- coding: utf-8 -*-
# Copyright (C) 2022 dvolkov

import time
from dataclasses import asdict
from compute.backend_dialect import BackendDialect
from compute.backend_product import BackendProduct

from compute.backend_target import BackendTarget
from lib.pgsql_client.pgsql_client import PgSqlClient, PgSqlClientException
from tabulate import tabulate

from .exceptions import BasePgSqlBackendException


class BasePgSqlBackend(PgSqlClient):
    """Generic class for PGSQL compatible backends"""

    clustered = False
    dialect = BackendDialect.pgsql
    product = BackendProduct.postgres

    def __init__(self, bt: BackendTarget):
        PgSqlClient.__init__(self, **asdict(bt))

    @staticmethod
    def pgsql_cli(cmd):
        """Simplify running multiply command via mysql command line"""
        return f"""sudo -i  -u postgres $SHELL -c 'psql' << EOF
        {cmd}
        EOF
        """

    def db_connect(self):
        try:
            self.connect()
        except PgSqlClientException as e:
            raise BasePgSqlBackendException(e)

    def self_test(self):
        self.db_connect()
        self.print_db_version()
        self.print_non_default_variables()

    def print_non_default_variables(self):
        query = """SELECT name, source, setting, unit FROM pg_settings WHERE source != 'default' AND source != 'override' and
        name not in ('application_name', 'client_encoding', 'DateStyle', 'default_text_search_config', 'TimeZone', 'max_stack_depth')
        and name not like ('log%') and name not like ('lc%') ORDER by 2, 1 """
        try:
            rows = self.select_all_rows(query)
            self.logger.info(f"\n{tabulate(rows)}")

        except PgSqlClientException as e:
            raise BasePgSqlBackendException(e)

    def print_db_size(self, database: str):
        # TODO: factor out repeated conn and cursor code into method
        try:
            size_query: str = (
                f"SELECT pg_size_pretty(pg_database_size('{database}')) as size"
            )
            row = self.select_one_row(size_query)
            self.logger.info(f"Total Database ({database}) size: \n{row.get('size')}")
        except PgSqlClientException as e:
            raise BasePgSqlBackendException(e)

    def pre_thread_run(self, **kwargs):
        pass

    def post_data_load(self, database: str):
        pass

    def pre_workload_run(self, **kwargs):
        pass

    def post_workload_run(self, **kwargs):
        pass

    def set_globals(self):
        """Set global variables for the instance"""
        self.db_connect()
        self.logger.info("Setting global variables")
        for k, v in self.config.globals.items():
            self.execute(f"set {k} = {v}")
