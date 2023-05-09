# -*- coding: utf-8 -*-
# Copyright (C) 2021 dvolkov


from ..exceptions import BackendException


class AuroraMySqlException(BackendException):
    """A Connection to database error occurred."""

class AuroraPostgreSqlException(BackendException):
    """A Connection to database error occurred."""