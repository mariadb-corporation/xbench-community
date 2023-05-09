import os

import pytest
from lib.vault.vault import VaultException
from lib.yaml_config import YamlConfig, YamlConfigException

os_home = os.getenv("HOME", "./")
xbench_home = os.getenv("XBENCH_HOME", "./")
base_dir = os.path.join(xbench_home, "test/integration/fixtures/")
filename_success = os.path.join(base_dir, "test_yaml_config_success.yaml")
filename_include = os.path.join(base_dir, "test_yaml_include.yaml")
filename_include_with_vault = os.path.join(base_dir, "test_yaml_include_with_vault.yaml")
filename_include_recursive = os.path.join(base_dir, "test_yaml_include_recursive.yaml")
filename_include_file = os.path.join(base_dir, "test_yaml_include_file_0.yaml")
vault_file = base_dir + "test_vault.yaml"
expected_vault_value = "yfqc1wugl3l7fv6q"
expected_defaults_with_vault = {
    "enterprise_download_token": "lneahz3g4jvzm8ct",
    "enable_prometheus_exporter": True,
    "prometheus_port": 9290,
}
expected_dict_success = {
    "conf_dir": f"{xbench_home}/conf",
    "clusters_dir": f"{os_home}/.xbench/clusters",
    "vault_file": f"{os_home}/.xbench/vault.yaml",
    "pem_dir": f"{os_home}/.xbench/pem",
    "certs_dir": f"{os_home}/.xbench/certs",
    "non_existent_env_var": "",
}


def test_load_yaml_config_file():
    yc = YamlConfig(filename_success)
    yaml_config_dict = yc.get_key()
    pytest.assume(yaml_config_dict == expected_dict_success)


def test_get_key():
    yc = YamlConfig(base_dir + "test_yaml_config_get_key.yaml")

    rootValStr = yc.get_key("testRootKeyString")
    pytest.assume(rootValStr == "^KKry5")

    rootValStr2 = yc.get_key(None, "testRootKeyString")
    pytest.assume(rootValStr2 == "^KKry5")

    rootNumVal = yc.get_key("testRootKeyNumber")
    pytest.assume(rootNumVal == 923471)

    rootNumBool = yc.get_key("testRootKeyBool")
    pytest.assume(rootNumBool == True)

    leafValStr = yc.get_key("testRoot", "testLeaf")
    pytest.assume(leafValStr == "6Mun{k")

    test_defaults_dict = yc.get_key("testRoot", None, True)
    expected_dict = {
        "enterprise_download_token": "VAULT['maxscale_download_token']",
        "enable_prometheus_exporter": True,
        "prometheus_port": 9290,
        "testLeaf": "6Mun{k",
    }
    pytest.assume(test_defaults_dict == expected_dict)

    test_defaults_override_dict = yc.get_key("testDefaultsOverride", None, True)
    expected_overrides_dict = {
        "enterprise_download_token": "VAULT['maxscale_download_token']",
        "enable_prometheus_exporter": True,
        "prometheus_port": 1019,
        "testLeaf": "m&.M4`",
    }
    pytest.assume(test_defaults_override_dict == expected_overrides_dict)


# The next two unit tests test VAULT['syntax'] on different levels
@pytest.fixture
def yc_with_vault():
    yc = YamlConfig(base_dir + "test_yaml_config_get_key.yaml", vault_file)
    return yc


def test_vault_child(yc_with_vault):
    yc = yc_with_vault

    test_leaf_with_vault = yc.get_key("db", "password")
    pytest.assume(test_leaf_with_vault == expected_vault_value)


def test_vault_root(yc_with_vault):
    yc = yc_with_vault

    test_parent = yc.get_key("db")
    test_child = test_parent.get("password")
    pytest.assume(test_child == expected_vault_value)


def test_vault_non_existent(yc_with_vault, capsys):
    yc = yc_with_vault

    with pytest.raises(YamlConfigException):
        _ = yc.get_key("vault_test", "non_existent")


def test_deep_tree_with_vault(yc_with_vault):
    yc = yc_with_vault

    expected_level_2_dict = {
        "leaf_node_level_three": "8zla3k",
        "vault_value_level_three": expected_vault_value,
        "deep_tree_level_three": {
            "leaf_node_level_four": "ga4xe8",
            "vault_value_level_four": expected_vault_value,
        },
    }

    test_node_level_2 = yc.get_key("deep_tree_root", "deep_tree_level_two")
    pytest.assume(test_node_level_2 == expected_level_2_dict)

    expected_level_2_dict_with_defaults = {
        **expected_level_2_dict,
        **expected_defaults_with_vault,
    }
    test_node_level_2_with_defaults = yc.get_key(
        "deep_tree_root", "deep_tree_level_two", True
    )
    pytest.assume(
        test_node_level_2_with_defaults == expected_level_2_dict_with_defaults
    )


def test_yaml_include():
    yc = YamlConfig(filename_include)
    expected_dict = {
        "root_key_1": "FGo8sbrZ2v3c",
        "include_key_1": expected_dict_success,
    }
    yaml_config_dict = yc.get_key()
    pytest.assume(yaml_config_dict == expected_dict)


def test_yaml_include_recursion():
    with pytest.raises(YamlConfigException) as err:
        _ = YamlConfig(filename_include_recursive)
    pytest.assume("not supported" in str(err))


def test_yaml_include_with_vault():
    yc = YamlConfig(filename_include_with_vault, vault_file)
    expected_dict = {
        "enterprise_download_token": "lneahz3g4jvzm8ct",
        "include_key_1": {
            "enterprise_download_token": "lneahz3g4jvzm8ct",
            "include_key_2": {
                "enterprise_download_token": "lneahz3g4jvzm8ct",
            },
        },
    }
    yaml_config_dict = yc.get_key()
    pytest.assume(yaml_config_dict == expected_dict)

def test_yaml_include_file():
    yc = YamlConfig(filename_include_file, vault_file)
    expected_dict = {
        "aws_xpand": {
            "cloud": "aws",
            "password": "yfqc1wugl3l7fv6q",
        },
        "skysql_test": {
            "cloud": "skysql",
        },
        "enterprise_download_token": "lneahz3g4jvzm8ct",
    }
    yaml_config_dict = yc.get_key()
    pytest.assume(yaml_config_dict == expected_dict)
