# -*- coding: utf-8 -*-
# Copyright (C) 2021 dvolkov

"""Python MariaDB client.

This module allows to do basic operations (select/insert/update) with mysql compatible database


"""

import logging
from decimal import ROUND_UP, Decimal
from os import path
from typing import Any, List, Optional

import mariadb

from .exceptions import (
    ConnectionException,
    InvalidQueryException,
    MariaDbClientException,
    NoDataFoundException,
)

DEFAULT_PORT = 3306
DEFAULT_HOST = "127.0.0.1"
DEFAULT_CONNECT_TIMEOUT = 5
DEFAULT_READ_TIMEOUT = 2

# DB Field information to be able to convert to Python types
fieldinfo = mariadb.fieldinfo()

float_typecodes = ["DECIMAL", "NEWDECIMAL", "FLOAT", "DOUBLE"]
int_typecodes = ["TINY", "SHORT", "INT24", "LONG"]
str_typecodes = ["VAR_STRING", "VARCHAR", "STRING"]

FLOAT_PRECISION = 2

# TODO check this implementation: https://github.com/PyMySQL/PyMySQL/
class MariaDbClient:
    def __init__(
        self,
        user: Optional[str] = None,
        password: Optional[str] = None,
        host: Optional[str] = None,
        port: Optional[int] = None,
        database: Optional[str] = None,
        connect_timeout: Optional[int] = None,
        read_timeout: int = None,
        ssl_ca: Optional[str] = None,
        ssl_cert: Optional[str] = None,
        ssl_key: Optional[str] = None,
        ssl: Optional[bool] = None,
        autocommit: Optional[bool] = None,
        **kwargs,
    ) -> None:
        """Initiate a Mariadb Client instance. If ssl requested, will check that ssl files exist

        Args:
           user (Optional[str], optional): Username. Defaults to None.
           password (Optional[str], optional): Password. Defaults to None.
           host (Optional[str], optional): Hostname. Defaults to None.
           port (Optional[int], optional): [description]. Defaults to None.
           database (Optional[str], optional): [description]. Defaults to None.
           connect_timeout (Optional[int], optional): [description]. Defaults to None.
           read_timeout (int, optional): [description]. Defaults to None.
           ssl_ca (Optional[str], optional): [description]. Defaults to None.
           ssl_cert (Optional[str], optional): [description]. Defaults to None.
           ssl_key (Optional[str], optional): [description]. Defaults to None.
           ssl (Optional[bool], optional): [description]. Defaults to None.
           autocommit (Optional[bool], optional): [description]. Defaults to None.

        """
        self.logger = logging.getLogger(__name__)
        self.conn = None
        self.cur = None
        self.user = user or kwargs.get("user")
        self.password = password or kwargs.get("password")
        self.host = host or kwargs.get("host") or DEFAULT_HOST
        self.port = port or kwargs.get("port") or DEFAULT_PORT
        self.database = database
        self.autocommit = (
            autocommit if autocommit is not None else kwargs.get("autocommit", False)
        )

        # Network timeouts
        self.connect_timeout = DEFAULT_CONNECT_TIMEOUT
        self.read_timeout = DEFAULT_READ_TIMEOUT

        # Chartset
        self.charset = "utf8"

        # SSL part
        self.ssl_ca = ssl_ca or kwargs.get("ssl_ca")  # ca.pem
        self.ssl_cert = ssl_cert or kwargs.get("ssl_cert")  # client-cert.pem
        self.ssl_key = ssl_key or kwargs.get("ssl_key")  # client-key.pem
        self.ssl = ssl if ssl is not None else kwargs.get("ssl", False)
        if self.ssl:
            self.check_ssl_config()

    def connect(self) -> None:
        """
        https://mariadb.com/resources/blog/how-to-connect-python-programs-to-mariadb/
        Connect to the database: https://github.com/mariadb-corporation/mariadb-connector-python/blob/9bb4e374ac65c5fd6b3bb6a15e227f2fe66dc519/mariadb/mariadb_connection.c
        Supported Keywords: https://github.com/mariadb-corporation/mariadb-connector-python/blob/88dcf20ebcdaef0502e59a9cdf234f46e7706eaf/doc/source/module.rst
        """
        try:
            self.logger.debug(
                f"Trying to connect to {self.host}:{self.port} as {self.user}"
            )
            self.conn = mariadb.connect(
                user=self.user,
                password=self.password,
                host=self.host,
                port=self.port,
                database=self.database,
                ssl_ca=self.ssl_ca,
                ssl_cert=self.ssl_cert,
                ssl_key=self.ssl_key,
                ssl=self.ssl,
                connect_timeout=self.connect_timeout,
                read_timeout=self.read_timeout,
                #  ssl_verify_cert=True - is not working so far
            )
            # https://mariadb-corporation.github.io/mariadb-connector-python/cursor.html
            self.cur = self.conn.cursor()
            self.logger.info(
                f"Successfully connected to {self.host}:{self.port} as {self.user}"
            )
        except mariadb.Error as e:
            raise ConnectionException(e)

    def print_db_version(self) -> None:
        """Print DB version
        MariaDb will have something like  10.4.7-MariaDB
        """
        row = self.select_one_row("select version()")
        self.logger.info(f"DB Engine version is {row[0]}")

    def execute(self, stmt: str) -> None:
        """Execute DDL or SET syntax statement

        Args:
            stmt (str): Statement to execute
        """
        try:
            self.cur.execute(stmt)
        except mariadb.ProgrammingError as e:
            raise InvalidQueryException(e)

    # ToDO: mariadb.InterfaceError: Lost connection to MySQL server during query
    def select_one_row(self, query: str) -> List:
        """Select first row from the result
        Args:
            query (str): Valid mysql query like
        """
        try:
            cur = self.cur
            cur.execute(query)
            row = cur.fetchone()
            if cur.rownumber == 0:
                raise NoDataFoundException(f"No Data found for query: {query}")
            return self.row_to_python(row, cur.description)
        except mariadb.ProgrammingError as e:
            raise InvalidQueryException(e)

    # TODO: check for expected data types: https://github.com/mariadb-corporation/mariadb-connector-python/blob/88dcf20ebcdaef0502e59a9cdf234f46e7706eaf/testing/test/integration/test_cursor.py#L399
    def select_all_rows(self, query: str) -> List[Any]:
        """Select all rows at once

        Args:
            query (str): Valid mysql query like
        """
        rows = []
        try:
            cur = self.cur
            cur.execute(query)
            for r in cur.fetchall():
                row = self.row_to_python(r, cur.description)
                rows.append(row)
            self.logger.debug(f"Found {cur.rowcount} row(s) for query {query}")
            return rows
        except mariadb.ProgrammingError as e:
            raise InvalidQueryException(e)

    def select_many_rows(self, query: str, num_rows: int = 1):
        """[Select number of rows at once]
        Args:
            query (str): [description]
        """
        # self.cur.arraysize = num_rows
        pass

    # ! handle None: import
    def row_to_python(self, row: tuple, cursor_description: tuple) -> List[Any]:
        # https://github.com/mariadb-corporation/mariadb-connector-python/blob/master/mariadb/constants/FIELD_TYPE.py
        # https://stackoverflow.com/questions/12661999/get-raw-decimal-value-from-mysqldb-query
        # https://github.com/mysql/mysql-connector-python/blob/master/lib/mysql/connector/conversion.py
        try:
            row_data = {}
            for i, data in enumerate(row):
                field_type = fieldinfo.type(
                    cursor_description[i]
                )  # This is MariaDB magic

                # Shouldn't I use Decimal?  # https://docs.python.org/3/library/decimal.html
                # # float(Decimal(data).quantize(Decimal(".01"), rounding=ROUND_UP))
                if field_type in float_typecodes:
                    row_data[cursor_description[i][0]] = round(
                        float(data), FLOAT_PRECISION
                    )
                elif field_type in str_typecodes:
                    row_data[cursor_description[i][0]] = str(data)
                elif field_type in int_typecodes:
                    row_data[cursor_description[i][0]] = (
                        None if data is None else int(data)
                    )
                elif field_type == "BLOB":
                    if isinstance(data, (bytes, bytearray)):
                        row_data[cursor_description[i][0]] = data.decode(self.charset)
                    else:
                        row_data[cursor_description[i][0]] = str(data)
                else:
                    print(data)
                    raise MariaDbClientException(
                        f"Not supported field type {field_type}"
                    )

            return row_data
        except TypeError as e:
            raise MariaDbClientException(f"{e} for {row} and {cursor_description}")

    def check_ssl_config(self):
        """Check if ssl files exists"""
        if not (
            path.exists(self.ssl_ca)
            and path.exists(self.ssl_key)
            and path.exists(self.ssl_cert)
        ):
            raise MariaDbClientException(
                f"SSL mode was requested, but one of the certs files does not exist"
            )
