import pytest
from compute import PsshClient, PsshClientException


@pytest.fixture
def pssh_client(aws_ssh_server):
    host_addr = aws_ssh_server.vm.network.public_ip
    return PsshClient(
        hostnames=[host_addr, host_addr],
        username="centos",
        key_file="~/.xbench/pem/MariaDBPerformance.pem",
    )


def test_failed_command_1(pssh_client):
    cmd = "I_am_none_existing_command"
    with pytest.raises(PsshClientException):
        pssh_client.run(cmd, timeout=10)


def test_output_from_list_1(pssh_client):
    """You can pass the list to one_command"""
    test_string = "Hello World"
    cmd = f"""
    date
    echo '{test_string}'
    """
    output = pssh_client.run(cmd, timeout=10)
    pytest.assume(len(output) == 2)
    pytest.assume(test_string in output[0].get("stdout"))


# def test_output_1(pssh_client):
#     test_string = "test me"
#     cmd = f"echo {test_string}"
#     r = pssh_client.run(cmd, timeout=10)
#     assert test_string in [l for l in r.get("vqc008d")[0]]


# def test_output_2(pssh_client):
#     test_string = "test me"
#     cmd = f"echo {test_string}"
#     r = pssh_client.run_shell(cmd, timeout=10, wait=True)
#     assert test_string in [l for l in r.get("vqc008d")[0]]


# def test_timeout_1(pssh_client):
#     """Task is about 20 sec timeout is 10 sec. This goes over retrying too"""
#     cmd = """
#     for i in {1..10}; do sleep 1; echo ${i}; done
#     """
#     with pytest.raises(PsshClientException):
#         pssh_client.run(cmd, timeout=10, wait=True)


def test_timeout_2(pssh_client):
    """Task is about 20 sec timeout is 10 sec"""
    cmd = """
    for i in {1..10}; do sleep 1; echo ${i}; done
    """
    with pytest.raises(PsshClientException):
        pssh_client.run(cmd, timeout=2)


# def test_complex_command(pssh_client):
#     cmd = "ls -la | grep root"
#     output = pssh_client.run(cmd, timeout=10, wait=True)
#     k = " ".join([l for l in output.get("vqc008d")[0]])  # string output
#     assert k.find("root") > 0


# def test_env_vars_command(pssh_client):
#     cmd = "echo $USER"  # there is no need for escaping
#     r = pssh_client.run(cmd, timeout=10, wait=True)
#     assert "root" in [l for l in r.get("vqc008d")[0]]
