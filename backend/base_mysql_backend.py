# -*- coding: utf-8 -*-
# Copyright (C) 2022 dvolkov


import time
from dataclasses import asdict
from compute.backend_dialect import BackendDialect

from compute.backend_target import BackendTarget
from lib.mysql_client.mysql_client import MySqlClient, MySqlClientException
from tabulate import tabulate

from .exceptions import BaseMySqlBackendException


class BaseMySqlBackend(MySqlClient):
    """Generic class for MySQL compatible backends"""

    dialect = BackendDialect.mysql

    def __init__(self, bt: BackendTarget):
        MySqlClient.__init__(self, **asdict(bt))

    @staticmethod
    def mysql_cli(cmd):
        """Simplify running multiply command via mysql command line"""
        return f"""mysql -A -s << EOF
        {cmd.replace("'", '"')}
        EOF
        """

    def db_connect(self):
        try:
            self.connect()
        except MySqlClientException as e:
            raise BaseMySqlBackendException(e)

    def create_database_and_user_stmt(self) -> str:
        # TODO ssl_clause = "REQUIRE SSL" if self.config.db.ssl is not None else ""
        ssl_clause = ""
        mysql_cmd = f"""
        create database if not exists {self.config.db.database};
        create user if not exists '{self.config.db.user}'@'%' identified by '{self.config.db.password}' {ssl_clause};
        grant all on *.* to '{self.config.db.user}'@'%' with grant option;
        flush privileges;
        """
        return mysql_cmd

    def create_database_and_user(self):
        self.run(self.mysql_cli(self.create_database_and_user_stmt()))

    def self_test(self):
        self.db_connect()
        self.print_db_version()
        self.print_non_default_variables()

    def print_non_default_variables(self):
        try:
            query = """select variable_name, global_value from INFORMATION_SCHEMA.SYSTEM_VARIABLES where global_value != coalesce(default_value, '')
            and variable_name not in ('BACK_LOG', 'BASEDIR', 'CHARACTER_SETS_DIR', 'HOSTNAME', 'FT_STOPWORD_FILE', 'INNODB_LOG_GROUP_HOME_DIR',
            'INNODB_VERSION', 'LC_MESSAGES_DIR', 'LICENSE', 'PID_FILE', 'PLUGIN_DIR', 'RELAY_LOG_INFO_FILE', 'SLAVE_LOAD_TMPDIR', 'PROTOCOL_VERSION',
            'GTID_BINLOG_POS', 'GTID_BINLOG_STATE', 'GTID_CURRENT_POS', 'SQL_BIG_SELECTS', 'SYSTEM_VERSIONING_ASOF', 'WSREP_PATCH_VERSION')
            and variable_name not like 'HAVE_%' and variable_name not like 'VERSION%' order by 1
            """
            rows = self.select_all_rows(query)
            self.logger.info(f"\n{tabulate(rows)}")

        except MySqlClientException as e:
            raise BaseMySqlBackendException(e)

    def print_db_size(self, database: str) -> None:
        """Print database size

        Args:
            database (str): database name
        """
        self.logger.info(f"ANALYZE TABLE(s) in schema '{database}'")
        query = f"SELECT GROUP_CONCAT(' ', CONCAT(table_schema, '.', table_name)) AS tables FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_SCHEMA='{database}'"
        row = self.select_one_row(query)
        query = f"ANALYZE TABLE {row.get('tables')}"
        self.select_all_rows(query)
        query = f"select ROUND(SUM(data_length + index_length) / 1024 / 1024 / 1024, 2) as  db_size FROM information_schema.TABLES where table_schema = '{database}'"
        row = self.select_one_row(query)
        self.logger.info(
            f"Total Database ({database}) size: \n{row.get('db_size')} (GB)"
        )

    def post_data_load(self, database: str):
        pass

    def pre_workload_run(self, **kwargs):
        pass

    def post_workload_run(self, **kwargs):
        pass

    def pre_thread_run(self, **kwargs):
        """This is running before each workload"""
        self.force_innodb_checkpoint()

    def force_innodb_checkpoint(self):
        self.db_connect()
        max_dirty_pages = self.select_one_row(
            "select @@innodb_max_dirty_pages_pct;"
        ).get("@@innodb_max_dirty_pages_pct")
        max_dirty_pages_lwm = self.select_one_row(
            "select @@innodb_max_dirty_pages_pct_lwm;"
        ).get("@@innodb_max_dirty_pages_pct_lwm")
        self.logger.info("Forcing InnoDB Checkpoint")
        self.execute("set global innodb_max_dirty_pages_pct=0;")
        buffer_pool_pages_dirty = int(
            self.select_one_row(
                "show global status like 'innodb_buffer_pool_pages_dirty';"
            ).get("Value")
        )
        self.logger.info("Waiting for buffer_pool to clear...")
        pages_dirty_old = 0
        repeat = 5
        while buffer_pool_pages_dirty >= 1000 and repeat >= 0:
            time.sleep(5)
            buffer_pool_pages_dirty = int(
                self.select_one_row(
                    "show global status like 'innodb_buffer_pool_pages_dirty';"
                ).get("Value")
            )
            self.logger.debug(f"Current dirty pages: {buffer_pool_pages_dirty}")
            if buffer_pool_pages_dirty == pages_dirty_old:
                repeat -= 1
            else:
                repeat = 5
            pages_dirty_old = buffer_pool_pages_dirty
        self.execute(f"set global innodb_max_dirty_pages_pct={max_dirty_pages};")
        self.execute(
            f"set global innodb_max_dirty_pages_pct_lwm={max_dirty_pages_lwm};"
        )
        self.execute("FLUSH HOSTS")
        self.logger.info("buffer_pool cleared")

    def set_globals(self):
        """Set global variables for the instance"""
        self.db_connect()
        self.logger.info("Setting global variables")
        for k, v in self.config.globals.items():
            self.execute(f"set global {k} = {v}")
