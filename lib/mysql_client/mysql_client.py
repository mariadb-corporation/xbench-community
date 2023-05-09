import inspect
import logging
from typing import Dict, Iterable, List, Optional

import pymysql
import pymysql.cursors  # https://github.com/PyMySQL/PyMySQL
import roundrobin
from common import backoff_with_jitter, retry

from .exceptions import (ConnectionException, InvalidQueryException,
                         MySqlClientException)


class MySqlClient:
    def __init__(self, **kwargs):
        self.connect_params = {
            k: v
            for k, v in kwargs.items()
            if k in inspect.signature(pymysql.connect).parameters
        }
        hosts = kwargs.get("host").split(",")
        get_roundrobin = roundrobin.basic(hosts)
        self.host = get_roundrobin()
        self.connect_params["host"] = self.host
        # Cursor class description http://kamushin.github.io/debug/sscursor_in_mysql.html
        self.connect_params["cursorclass"] = pymysql.cursors.DictCursor
        self.logger = logging.getLogger(__name__)
        self.conn = None
        self.cur = None

    @retry(
        pymysql.Error,
        ConnectionException,
        delays=backoff_with_jitter(delay=3, attempts=10, cap=10),
    )
    def connect(self) -> None:

        self.logger.debug(f"Trying to connect to mysql {self.host} {self.connect_params}")
        self.conn = pymysql.connect(**self.connect_params)
        self.cur = self.conn.cursor()
        self.logger.debug(f"Successfully connected to mysql {self.host}")

    def print_db_version(self) -> None:
        """Print DB version
        MariaDb will have something like  10.4.7-MariaDB
        """
        row = self.select_one_row("select version()")
        self.logger.info(f"DB Engine version is {row.get('version()')}")

    @retry(
        (pymysql.Error, pymysql.OperationalError),
        MySqlClientException,
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
        except pymysql.ProgrammingError as e:
            raise InvalidQueryException(e)

    @retry(
        (pymysql.Error, pymysql.OperationalError),
        MySqlClientException,
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
        except pymysql.ProgrammingError as e:
            raise InvalidQueryException(e)

    @retry(
        (pymysql.Error, pymysql.OperationalError),
        MySqlClientException,
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
        except pymysql.ProgrammingError as e:
            raise InvalidQueryException(e)
