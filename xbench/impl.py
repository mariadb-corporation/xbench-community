# -*- coding: utf-8 -*-
# Copyright (C) 2021 dvolkov


import os
import logging
from .exceptions import XbenchException
from yaml_config import YamlConfig


class Impl:
    def __init__(self, impl_name, xbench_config):
        """Implement one entry from impl.yaml"""
        self.logger = logging.getLogger(__name__)

        self.impl_name = impl_name
        self.xbench_config = xbench_config
        self.conf_dir = self.xbench_config.get("conf_dir")
        self.impl_dict = None

        self.load_impl_config()

    def load_impl_config(self):

        impl_yaml_file = os.path.join(self.conf_dir, "impl.yaml")
        vault_file = self.xbench_config.get("vault")
        impl_yaml = YamlConfig(yaml_config_file=impl_yaml_file, vault=vault_file)
        self.impl_dict = impl_yaml.get_key(self.impl_name)

    def get_cloud_class(self):
        """Get Cloud provider Class Instance"""

        cloud = self.impl_dict.get("cloud", "aws")
        region = self.impl_dict.get("region", "us-west-2")

        # Load cloud yaml
        cloud_yaml_file = os.path.join(self.conf_dir, "cloud.yaml")
        cloud_yaml = YamlConfig(yaml_config_file=cloud_yaml_file)
        cloud_dict = cloud_yaml.get_key(root="providers", leaf=cloud)
        print(cloud_dict.get("regions")[region])


        # https://stackoverflow.com/questions/4821104/dynamic-instantiation-from-string-name-of-a-class-in-dynamically-imported-module
        # import importlib
        # module = importlib.import_module(module_name)
        # class_ = getattr(module, class_name)
        # instance = class_()

        pass
