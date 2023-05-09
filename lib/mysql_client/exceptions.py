#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright (C) 2021 dvolkov


class MySqlClientException(Exception):
    """An HTTP error occurred."""

    def __init__(self, err_message=None):
        self.err_message = err_message

    def __str__(self):
        return "{err_message}".format(err_message=self.err_message)


class LoginException(MySqlClientException):
    """A login error occurred."""


class ConnectionException(MySqlClientException):
    """A Connection error occurred."""


class InvalidQueryException(MySqlClientException):
    """An HTTP error occurred."""


class NoDataFoundException(MySqlClientException):
    """No Data Found during the query occurred."""


class TooManyRowsException(MySqlClientException):
    """Too many rows during a single row query occurred."""
