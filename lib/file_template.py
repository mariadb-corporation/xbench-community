# -*- coding: utf-8 -*-
# Copyright (C) 2021 dvolkov


import logging
import os
from typing import Optional

from jinja2 import StrictUndefined, Template
from jinja2.exceptions import UndefinedError

from .xbench_config import XbenchConfig


class FileTemplateException(Exception):
    """An Xbench config exception occurred."""


class FileTemplate:
    """Read file from the local disk and substitute variables

    Raises:
        FileTemplateException: something went wrong

    """

    def __init__(self, filename: str, dir: Optional[str] = None):

        self.filename = filename
        self.logger = logging.getLogger(__name__)
        self.fqn = os.path.join(dir or XbenchConfig().config_dir, self.filename)

    def render(self, *args, **kwargs) -> str:
        try:
            with open(self.fqn) as f:
                rendered = Template(f.read(), undefined=StrictUndefined).render(
                    *args, **kwargs
                )
            return rendered
        except (IOError, FileNotFoundError, UndefinedError) as e:
            raise FileTemplateException(e)
