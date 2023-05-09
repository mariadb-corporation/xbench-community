# -*- coding: utf-8 -*-
# Copyright (C) 2021 dvolkov


from ..exceptions import BackendException


class MariaDBException(BackendException):
    """A Connection to database error occurred."""
