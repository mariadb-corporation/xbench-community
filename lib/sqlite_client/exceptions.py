#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright (C) 2021 dvolkov


class SQLiteClientException(Exception):
    """SQL lite error occurred"""

    def __init__(self, err_message=None):
        self.err_message = err_message

    def __str__(self):
        return "{err_message}".format(err_message=self.err_message)
