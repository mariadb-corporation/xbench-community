import pytest
from compute import SshClient, SshClientException

HOSTNAME = "IamnoExsiting"


@pytest.fixture
def ssh_client():
    return SshClient(hostname=HOSTNAME, username="root", key_file="~/.ssh/id_rsa")


def test_command_1(ssh_client):
    cmd = "hostname"
    with pytest.raises(SshClientException):
        ssh_client.run(cmd)
