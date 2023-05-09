import pytest
from lib.file_template import FileTemplate, FileTemplateException, XbenchConfig

params = {
    "mariadb": {
        "user": "xbench",
        "password": "secret",
        "port": 3306,
        "host": "127.0.0.1",
        "ssl": False,
    },
    "system": {
        "buffer_pool_size": 60,
        "memory": 72,  # Nenory in Gb
        "cpu": 32,
    },
    "config": {"binlog": False, "data_dir": "/data/mariadb"},
}


def buffer_pool(memory_gb):
    round(max(0.8 * memory_gb, memory_gb - 10), 0)


@pytest.fixture
def ft():
    XbenchConfig().initialize()
    ft = FileTemplate(filename="mariadb_performance.cnf")
    yield ft


def test_missing_file(ft):

    with pytest.raises(FileTemplateException):
        render = ft.render(**params)


def test_successfully_render_ssl(ft):

    render = ft.render(**params)
    print(render)
    pytest.assume("skip-log-bin" in render)

    # assert False  # - best way to see output


# def test_successfully_render_no_ssl(ft):
#     params["maxscale"]["ssl"] = False
#     render = ft.render(**params)
#     pytest.assume("ssl_ca_cert" not in render)


# def test_missing_params(ft):

#     params = {"port": 3306}

#     with pytest.raises(FileTemplateException):
#         render = ft.render(**params)
