import logging
import shlex

import pytest
from compute import PsshClient, PsshClientException

mysql_cmd = """
create database if not exists bla_bla;
create user if not exists  'user1'@'%' identified by 'q';
select @@version;
"""

shell_cmd = """
ls -la 
date
hostname
"""


def mysql_cli(cmd):
    return f"""mysql -A -s << EOF
    {cmd.replace("'", '"')}
    EOF
    """


# Executing command 'b"sudo -S $SHELL -c 'mysql -s << EOF\ncreate user if not exists  'user1'@'%' identified by 'q';\nEOF'"'
# create user if not exists  user1@% identified by q

# cmd = shlex.quote(cmd)
# cmd = cmd.replace("'", '"')
logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    level="DEBUG",
)

p = PsshClient(hostname="yang01a", username="root")
p.run(cmd=mysql_cli(mysql_cmd), timeout=300, sudo=True)
p.run(cmd=shell_cmd, sudo=True)
