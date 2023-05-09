import os

import pytest
import xmltodict

xbench_home = os.getenv("XBENCH_HOME", "./")
base_dir = os.path.join(xbench_home, "test/integration/fixtures/")

xml_test_filename = os.path.join(base_dir, "test.xml")


@pytest.fixture
def data():
    with open(xml_test_filename) as xml:
        data = xmltodict.parse(xml.read())
    yield data


@pytest.mark.order(1)
def test_read_property(data):
    pytest.assume(data["parameters"]["terminals"] == "1")


@pytest.mark.order(2)
def test_write_test(data):
    write_file_name = "/tmp/result.xml"
    new_data = data
    new_data["parameters"]["terminals"] = "128"
    print(xmltodict.unparse(new_data, pretty=True))
    with open(write_file_name, "w") as result_file:
        result_file.write(
            xmltodict.unparse(new_data, pretty=True)
        )  # it does encoding='utf-8' by default

    with open(write_file_name) as xml:
        updated_data = xmltodict.parse(xml.read())

    pytest.assume(updated_data["parameters"]["terminals"] == "128")
