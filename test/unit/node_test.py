import os

import pytest
from compute import Node
from compute.exceptions import NodeException, SshClientException


@pytest.fixture
def node(aws_ssh_server):
    yield Node(aws_ssh_server.vm)


def test_node_copy(node):
    node.send_file("test/integration/fixtures/ca.pem", "/tmp/ca.pem")
    output = node.run("ls -la /tmp")
    pytest.assume("ca.pem" in output)
