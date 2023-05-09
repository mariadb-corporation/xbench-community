# -*- coding: utf-8 -*-
# Copyright (C) 2021 dvolkov


import logging
import os
import tempfile
import re
from abc import abstractmethod, abstractproperty
from ast import Str
from types import GeneratorType
from typing import Any, Dict, List, Union

import yaml
from common import recursive_items
from lib.vault import Vault, VaultException

INCLUDE_MARKER = "!include"
YAML_DOCUMENT_SEPARATOR = "---"

class YamlDictNodeReader(object):
    """
    Dictionary node reader abstract base class.
    Parses YAML node values in the format `DICT['key']` using regular expressions.
    Class `YamlDictNodeReader` must be derived. It is not intended to be used directly.

    Examples:
     - `EnvYamlDictNodeReader(YamlDictNodeReader)` class provides implementation for reading OS variable values using ENV['var_name'] syntax in YAML, e.g.:

        #sample YAML snippet \n
        conf_dir: ENV['XBENCH_HOME']/conf

     - `VaultYamlDictNodeReader(YamlDictNodeReader)` class provides implementation for reading from the Vault using VAULT['key'] syntax in YAML.

        #sample YAML snippet \n
        db:
          password: VAULT['xbench_db_password']

    How to use:
    1. Derive from `YamlDictNodeReader` and provide implementation for these class members:
       `name()` property getter
       `read_value(key: str)` virtual method
    2. Add an instance of your custom node reader class to `YamlConfig._nodeReadersList` in YamlConfig's constructor.
    """

    def __init__(self):
        self.logger = logging.getLogger(__name__)

    @abstractproperty
    def name(self):
        pass

    @abstractmethod
    def read_value(self, key: str):
        pass

    @property
    def pattern(self):
        return rf"{self.name}\[\'(.*?)\'\]"

    def pathex_constructor(self, loader, node):
        value = loader.construct_scalar(node)
        try:
            pattern = self.pattern
            return re.sub(pattern, lambda m: self.read_value(m.group(1)), value)

        except KeyError:
            # This is lazy evaluation - it could cause issue if silently ignored
            return value


class EnvYamlDictNodeReader(YamlDictNodeReader):
    @property
    def name(self):
        return "ENV"

    def read_value(self, key: str):
        value = os.getenv(key)
        if value is None:
            self.logger.warning(f"Environment variable {key} is not set")
        return os.getenv(key)


class VaultYamlDictNodeReader(YamlDictNodeReader):
    def __init__(self, vault: Vault):
        self.vault = vault
        super().__init__()

    @property
    def name(self):
        return "VAULT"

    def read_value(self, key: str):
        try:
            val = self.vault.get_secret(key)
            return val
        except VaultException as e:
            self.logger.warning(f"Secret {key} is missing in the vault")
            return None

class YamlConfigException(Exception):
    """
    Exception specific to Yaml execution
    """

    def __init__(self, err_message=None):
        self.err_message = err_message

    def __str__(self):
        return "{err_message}".format(err_message=self.err_message)


class YamlConfig(object):
    """
    Represent config from yaml file
    """

    _nodeReadersList: List[YamlDictNodeReader] = []

    def __init__(self, yaml_config_file, vault_file: str = None):

        self.logger = logging.getLogger(__name__)

        self.vault = Vault(vault_file) if vault_file else None

        self._nodeReadersList.append(EnvYamlDictNodeReader())
        self._nodeReadersList.append(
            VaultYamlDictNodeReader(self.vault)
        ) if self.vault else None

        self.yaml_config_file = yaml_config_file
        self._yaml_config_dict = self.load_yaml_config_file(yaml_config_file)
        self.defaults = None

        try:
            self.defaults = self._yaml_config_dict.get("defaults", None)
        except (KeyError, YamlConfigException) as e:  # we might don't have defaults
            pass

    @property
    def yaml_config_dict(self):
        return self.get_key()

    @yaml_config_dict.setter
    def yaml_config_dict(self, value):
        self._yaml_config_dict = value

    def include(self, loader, node):
        root = os.path.split(loader.stream.name)[0]
        filename = os.path.join(root, loader.construct_scalar(node))
        if filename == loader.stream.name:
            raise YamlConfigException(f"Recursion is not supported with {INCLUDE_MARKER} tags. File includes itself: {filename}")

        with open(filename, 'r') as f:
            return yaml.load(f, Loader=type(loader))

    def load_yaml_config_file(self, yaml_config_file):
        """
        Load yaml file and replace ENV variables (if any)
        :return: dict
        """
        if os.path.exists(yaml_config_file):
            try:
                for nr in self._nodeReadersList:
                    name = nr.name
                    pattern = nr.pattern
                    rx = re.compile(pattern)
                    yaml.add_implicit_resolver(name, rx)
                    yaml.add_constructor(name, nr.pathex_constructor)
                yaml.add_constructor(INCLUDE_MARKER, self.include)

                yaml_config_file = self.analyze_includes(yaml_config_file)

                with open(yaml_config_file, "rt") as f:
                    yaml_config_dict = yaml.load_all(f, Loader=yaml.Loader)
                
                    if isinstance(yaml_config_dict, GeneratorType):
                        res = None
                        for y in yaml_config_dict:
                            if res:
                                res.update(y)
                            else:
                                res = y
                        yaml_config_dict = res

                self.logger.debug(f"Config file {yaml_config_file} successfully opened")
                return yaml_config_dict

            except (yaml.YAMLError, yaml.MarkedYAMLError) as exc:

                if exc.context is not None:
                    message = (
                        "\n"
                        + str(exc.problem_mark)
                        + "\n  "
                        + str(exc.problem)
                        + " "
                        + str(exc.context)
                    )
                else:
                    message = "\n" + str(exc.problem_mark) + "\n  " + str(exc.problem)
                raise YamlConfigException(
                    "En error occurred during the %s parsing: %s "
                    % (yaml_config_file, message)
                )

        else:
            message = "Config file %s not found" % yaml_config_file
            raise YamlConfigException(message)

    def get_key(self, root: str = None, leaf: str = None, use_defaults: bool = False):
        """
        Load profile from config.yaml

        :param root: root level key name
        :param leaf: next level key name
        :use_defaults: whether add the defaults or not
        :return: a key from yaml file under root [and leaf]
        """
        config = self._yaml_config_dict
        if root and leaf:
            ret = config[root].get(leaf, None)
        elif root and not leaf:
            ret = config.get(root, None)
        elif leaf and not root:
            ret = config.get(leaf, None)
        else:
            ret = config
        if ret is not None:
            if use_defaults and self.defaults and isinstance(ret, dict):
                ret = (
                    self.defaults | ret.copy()
                    if any(
                        isinstance(v, dict) for k, v in ret.items()
                    )  # If it is nested do not add defaults
                    else self.save_dict_merge(self.defaults.copy(), ret.copy())
                )
            if self.is_empty(ret):
                raise YamlConfigException(
                    f"[{leaf}] or [{root}] end up with empty values"
                )
            else:
                return ret
        else:
            message = f"One of the [{leaf}] or [{root}] are not defined in config file {self.yaml_config_file} "
            raise YamlConfigException(message)

    @staticmethod
    def is_empty_simple_key(val: Any):
        if isinstance(val, str):
            if val == "" or val is None:
                return True
        else:
            if val is None:
                return True
        return False

    def is_empty(self, ret: Any):
        if isinstance(ret, dict):
            for k, v in recursive_items(ret):
                return self.is_empty_simple_key(v)
        else:
            return self.is_empty_simple_key(ret)

    @staticmethod
    def save_dict_merge(dict1, dict2):
        if dict2 is None:
            dict2 = {}
        dict_merge = lambda a, b: a.update(b) or a
        result = dict_merge(dict1, dict2)
        return result

    def analyze_includes(self, yaml_filename) -> str:
        if not os.path.exists(yaml_filename):
            return yaml_filename
        
        rx = re.compile(rf"{INCLUDE_MARKER}\s+(.+)")
        content: str = ""
        ext_files_dict: dict = {}
        with open(yaml_filename, "rt") as f:
            content = f.read()
            for m in rx.finditer(content):
                expr = m.group(0)
                fn = m.group(1)
                ext_files_dict[expr] = fn
        
        if len(ext_files_dict) == 0:
            return yaml_filename

        content = content.replace(YAML_DOCUMENT_SEPARATOR, "")

        msg : str = ""
        base_path = os.path.split(yaml_filename)[0]
        for expr in ext_files_dict:
            fn = ext_files_dict[expr]
            fn_full = f"{base_path}/{fn}"
            file_content = ""
            if os.path.exists(fn_full):
                msg += f"""{", " if len(msg)>0 else ""}{fn}"""
                with open(fn_full, "r") as ef:
                    file_content = ef.read()
            content = content.replace(expr, file_content)
        
        with tempfile.NamedTemporaryFile(suffix=".yaml", delete=False) as fp:
            fp.write(content.encode())
            msg = f"YAML file {yaml_filename} and its includes ({msg}) serialized to a single YAML file: {fp.name}"
            self.logger.debug(msg)
            return fp.name

        