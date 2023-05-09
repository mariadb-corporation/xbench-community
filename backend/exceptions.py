# -*- coding: utf-8 -*-
# Copyright (C) 2021 dvolkov


class BackendException(Exception):
    """An HTTP error occurred."""

    def __init__(self, err_message=None):
        self.err_message = err_message

    def __str__(self):
        return "{err_message}".format(err_message=self.err_message)


class BaseMySqlBackendException(BackendException):
    """Base MySql exception"""

class BasePgSqlBackendException(BackendException):
    """Base MySql exception"""
