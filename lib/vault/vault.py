# -*- coding: utf-8 -*-
# Copyright (C) 2021 dvolkov


import logging
import os

import yaml


class VaultException(Exception):
    """
    Exception specific to Vault execution
    """


class Vault:
    """
    Represent vault which located in client machine
    """

    def __init__(self, vault_file):

        self.logger = logging.getLogger(__name__)
        self.vault_config_dict = self.load_yaml_config_file(vault_file)

    def load_yaml_config_file(self, vault_file):

        if os.path.exists(vault_file):
            try:
                with open(vault_file, "rt") as f:
                    vault_config_dict = yaml.load(f, Loader=yaml.Loader)
                    self.logger.debug(f"Config file {vault_file} successfully opened")
                    return vault_config_dict

            except (yaml.YAMLError, yaml.MarkedYAMLError) as e:
                raise VaultException(
                    f"En error {e} occurred during the parsing {vault_file}"
                )

        else:
            raise VaultException(f"Config file {vault_file} not found")

    def get_secret(self, secret: str):

        secret_value = self.vault_config_dict.get(secret, None)
        if not secret_value:
            raise VaultException(f"there is no secret {secret}")
        return secret_value
