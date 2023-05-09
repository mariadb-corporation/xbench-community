import inspect
import logging
from typing import Dict, Iterable, List, Optional

import psycopg2
import psycopg2.extras
import roundrobin
from common import backoff_with_jitter, retry

from .exceptions import (ConnectionException, InvalidQueryException,
                         PgSqlClientException)


class PgSqlClient:
    def __init__(self, **kwargs):
        # TODO Handle autocommit properly
        self.connect_params = {
            k: v
            for k, v in kwargs.items()
            if k in ['host', 'port', 'user', 'password', 'database', 'connect_timeout']
        }
        self.logger = logging.getLogger(__name__)
        hosts = kwargs.get("host").split(",")
        get_roundrobin = roundrobin.basic(hosts)
        self.host = get_roundrobin()
        self.connect_params["host"] = self.host
        self.connect_params["cursor_factory"] = psycopg2.extras.RealDictCursor
        self.conn = None
        self.cur = None

    @retry(
        psycopg2.Error,
        ConnectionError,
        delays=backoff_with_jitter(delay=3, attempts=10, cap=10),
    )
    def connect(self) -> None:

        self.logger.debug(f"Trying to connect to pgsql {self.host} using {self.connect_params}")
        self.conn = psycopg2.connect(**self.connect_params)
        self.conn.set_isolation_level(psycopg2.extensions.ISOLATION_LEVEL_AUTOCOMMIT)
        self.cur = self.conn.cursor()
        self.logger.debug(f"Successfully connected to pgsql on {self.host}")

    def print_db_version(self) -> None:
        """Print DB version

        """
        row = self.select_one_row("select version()")
        self.logger.info(f"DB Engine version is {row.get('version')}")

    @retry(
        (psycopg2.Error, psycopg2.OperationalError),
        PgSqlClientException,
        delays=backoff_with_jitter(delay=3, attempts=10, cap=10),
    )
    def select_one_row(
        self, query: str, params: Optional[Iterable[tuple]] = None
    ) -> Dict:
        """Select first row from the result
        Args:
            query (str): Valid mysql query like
        """
        try:
            cur = self.cur
            cur.execute(query, params)
            row = cur.fetchone()
            return row if cur.rownumber > 0 else {}
        except psycopg2.ProgrammingError as e:
            raise InvalidQueryException(e)

    @retry(
        (psycopg2.Error, psycopg2.OperationalError),
        PgSqlClientException,
        delays=backoff_with_jitter(delay=3, attempts=3, cap=10),
    )
    def select_all_rows(
        self, query: str, params: Optional[Iterable[tuple]] = None
    ) -> List[Dict]:
        """Select all rows at once

        Args:
            query (str): Valid mysql query like
        """
        try:
            cur = self.cur
            cur.execute(query, params)
            rows = cur.fetchall()
            self.logger.debug(f"Found {cur.rowcount} row(s) for query {query}")
            return rows
        except psycopg2.ProgrammingError as e:
            raise InvalidQueryException(e)

    @retry(
        (psycopg2.Error, psycopg2.OperationalError),
        PgSqlClientException,
        delays=backoff_with_jitter(delay=5, attempts=15, cap=60),
    )
    def execute(self, query: str, params: Optional[Iterable[tuple]] = None):
        """Run insert,update, delete or DML query

        Args:
            query (str): [description]
            params (tuple): [description]

        Returns:
            [type]: [description]
        """
        try:
            self.cur.execute(query, params)
            return self.cur.rowcount  # Return how many values has been updated
        except psycopg2.ProgrammingError as e:
            raise InvalidQueryException(e)
