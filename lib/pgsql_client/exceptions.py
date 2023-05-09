#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright (C) 2021 dvolkov


class PgSqlClientException(Exception):
    """ Generic client exception"""

    def __init__(self, err_message=None):
        self.err_message = err_message

    def __str__(self):
        return "{err_message}".format(err_message=self.err_message)


class LoginException(PgSqlClientException):
    """A login error occurred."""


class ConnectionException(PgSqlClientException):
    """A Connection error occurred."""


class InvalidQueryException(PgSqlClientException):
    """An HTTP error occurred."""


class NoDataFoundException(PgSqlClientException):
    """No Data Found during the query occurred."""


class TooManyRowsException(PgSqlClientException):
    """Too many rows during a single row query occurred."""
