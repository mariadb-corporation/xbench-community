import pytest
from lib.file_template import FileTemplate, FileTemplateException, XbenchConfig

params = {
    "xpand": {
        "user": "xpand",
        "password": "secret",
        "port": 3306,
        "host": "127.0.0.1",
    },
    "maxscale": {
        "port": 3306,
        "ssl": True,
    },
}


@pytest.fixture
def ft():
    XbenchConfig().initialize()
    ft = FileTemplate(filename="maxscale_xpand.cnf")
    yield ft


@pytest.fixture
def bad_ft():
    XbenchConfig().initialize()
    ft = FileTemplate(filename="I am not existing")
    yield ft


def test_missing_file(bad_ft):
    params = {"port": 3306}

    with pytest.raises(FileTemplateException):
        render = bad_ft.render(**params)


def test_successfully_render_ssl(ft):

    render = ft.render(**params)
    pytest.assume("127.0.0.1" in render)
    pytest.assume("ssl_ca_cert" in render)

    # assert False  # - best way to see output


def test_successfully_render_no_ssl(ft):
    params["maxscale"]["ssl"] = False
    render = ft.render(**params)
    pytest.assume("ssl_ca_cert" not in render)


def test_missing_params(ft):

    params = {"port": 3306}

    with pytest.raises(FileTemplateException):
        render = ft.render(**params)
