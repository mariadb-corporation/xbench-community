# -*- coding: utf-8 -*-
# Copyright (C) 2021 dvolkov


import logging
import os

from lib.yaml_config import YamlConfig, YamlConfigException


class XbenchConfigException(Exception):
    """An Xbench config exception occurred."""


class XbenchConfig:
    """Singleton class to hold global settings for the project

    Raises:
        XbenchException: [description]

    Returns:
        [type]: [description]
    """

    __instance = None
    __cluster_name = None

    def __new__(cls, *args, **kwargs):
        if not XbenchConfig.__instance:
            XbenchConfig.__instance = object.__new__(cls)
            XbenchConfig.__cluster_name = kwargs.get("cluster_name", None)
        return XbenchConfig.__instance

    def initialize(self):
        self.logger = logging.getLogger(__name__)
        self.config = self.get_config()
        self.config_dir = self.config.get("conf_dir")

    @property
    def xbench_config(self):
        return self.config

    @staticmethod
    def cluster_name():
        return XbenchConfig.__cluster_name

    @staticmethod
    def xbench_home():
        xbench_home = os.getenv("XBENCH_HOME")
        if not xbench_home:
            raise XbenchConfigException("XBENCH_HOME environment variable is missing")
        else:
            return xbench_home

    def get_config(self):
        """Looking for xbench config file
        Use XBENCH_CONFIG environmental variable if exists, then look in user $HOME, then in XBENCH_HOME
        Raises:
            XbenchException: if not found

        Returns:
            [type]: [description]
        """
        xbench_config_file = os.getenv("XBENCH_CONFIG")
        if not xbench_config_file:
            home = self.xbench_home()
            xbench_config_file = f"{home}/.xbench/xbench_config.yaml"
            if not os.path.isfile(xbench_config_file):
                xbench_config_file = f"{os.getenv('XBENCH_HOME')}/xbench_config.yaml"
                if not os.path.isfile(xbench_config_file):
                    raise XbenchConfigException("Unable to locate xbench_config.yaml")

        self.logger.debug(f"Using {xbench_config_file} as xbench config yaml")
        ya = YamlConfig(yaml_config_file=xbench_config_file)
        return ya.yaml_config_dict

    def get_key(self, key):
        """Internal function for Xbench config"""
        value = self.config.get(key, None)
        if not value:
            raise XbenchConfigException(f"Key {key} is not defined")
        return value

    def get_key_from_yaml(self, yaml_file_name: str, key_name: str, use_defaults: bool):
        try:
            yaml = self.load_yaml(yaml_file_name)
            return yaml.get_key(key_name, use_defaults=use_defaults)
        except YamlConfigException as e:
            raise XbenchConfigException(e)

    def load_yaml(self, yaml_file_name: str):
        try:
            # Load topology
            yaml_file = os.path.join(self.config_dir, yaml_file_name)
            yaml = YamlConfig(
                yaml_config_file=yaml_file,
                vault_file=self.config.get("vault_file"),
            )  # topo shouldn't have any vault specific info
            return yaml
        except YamlConfigException as e:
            raise XbenchConfigException(e)
