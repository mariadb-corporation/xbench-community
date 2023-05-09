import pytest
from compute import SshClient, SshClientException


@pytest.fixture
def ssh_client(aws_ssh_server):
    host_addr = aws_ssh_server.vm.network.public_ip
    return SshClient(
        hostname=host_addr,
        username="centos",
        key_file="~/.xbench/pem/MariaDBPerformance.pem",
    )


def test_failed_command_1(ssh_client):
    cmd = "I_am_none_existing_command"
    with pytest.raises(SshClientException):
        ssh_client.run(cmd)


def test_ignore_failed_command_1(ssh_client):
    cmd = "I_am_none_existing_command"
    output = ssh_client.run(cmd, ignore_errors=True)


def test_output_1(ssh_client):
    test_string = "test me"
    cmd = f"echo {test_string}"
    output = ssh_client.run(cmd)
    assert test_string in output


def test_output_sudo_1(ssh_client):
    test_string = "test me"
    cmd = f"echo {test_string}"
    output = ssh_client.run(cmd, sudo=True)
    assert test_string in output


def test_timeout_1(ssh_client):
    """Task is about 20 sec timeout is 10 sec. This goes over retrying too"""
    cmd = """
    for i in {1..10}; do sleep 1; echo ${i}; done
    """
    with pytest.raises(SshClientException):
        ssh_client.run(cmd, timeout=10)

def test_multiline():
    key_file = "~/.xbench/pem/gcp_key.pem"
    host_addr = "35.193.170.163"
    ssh_client = SshClient(
        hostname=host_addr,
        username="clustrix",
        key_file=key_file,
    )
    failing_command_without_output = "grep -i bla /etc/passwd"
    failing_command_with_output = "cat /i_dont_exist"
    cmd = f"""
     cd /dev
     rm -rf test_ssh_multiline
     {failing_command_with_output}
     mkdir test_ssh_multiline
     """
    output = ssh_client.run(cmd, sudo=True, ignore_errors=False)
    # output = ssh_client.run(cmd, sudo=True, ignore_errors=True)
    assert 'error' not in output