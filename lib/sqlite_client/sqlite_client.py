import logging
import sqlite3
from typing import Any, Dict, Iterable, List

from .exceptions import SQLiteClientException


class SQLiteClient:
    def __init__(self, db_name):
        self.db_name = db_name
        self.logger = logging.getLogger(__name__)
        self.conn = None
        self.cur = None

    @staticmethod
    def dict_factory(cursor, row):
        d = {}
        for idx, col in enumerate(cursor.description):
            d[col[0]] = row[idx]
        return d

    def connect(self) -> None:
        self.conn = sqlite3.connect(
            self.db_name,
            isolation_level=None,  # This set autocommit on
            check_same_thread=False,
        )
        self.conn.row_factory = self.dict_factory

        self.cur = self.conn.cursor()

    def execute(self, query: str, params: Iterable[Any] = []):
        try:
            self.cur.execute(query, params)
            return self.cur.rowcount  # Return how many values has been updated
        except sqlite3.Error as e:
            raise SQLiteClientException(e)

    def select_all_rows(self, query: str, params: Iterable[Any] = []) -> List[Dict]:
        """
        Args:
            query (str): query
            params (Iterable[Any], optional): parameters if any . Defaults to [].

        Returns:
            List[Dict]:[{'id': 1, 'dtime': '2022-05-05 19:34:11'}, {'id': 1, 'dtime': '2022-05-05 19:34:12'}]
        """
        try:
            rows = self.cur.execute(query, params).fetchall()
            return rows
        except sqlite3.Error as e:
            raise SQLiteClientException(e)
