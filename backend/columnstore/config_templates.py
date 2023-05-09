# -*- coding: utf-8 -*-
# Copyright (C) 2021 detravi


storagemanager_cnf="""
[ObjectStorage]
service = S3
object_size = 5M
metadata_path = /var/lib/columnstore/storagemanager/metadata
journal_path = /var/lib/columnstore/storagemanager/journal
max_concurrent_downloads = 21
max_concurrent_uploads = 21
common_prefix_depth = 3

[Cache]
cache_size = 2g
path = /var/lib/columnstore/storagemanager/cache

[S3]
bucket                = {bucket}
endpoint              = s3.amazonaws.com
region                = {aws_region}
aws_access_key_id     = {aws_access_key_id}
aws_secret_access_key = {aws_secret_access_key}
"""

mcs_cluster_cnf="""
[mariadb]
bind_address                           = 0.0.0.0
log_error                              = mariadbd.err
character_set_server                   = utf8
collation_server                       = utf8_general_ci
log_bin                                = mariadb-bin
log_bin_index                          = mariadb-bin.index
relay_log                              = mariadb-relay
relay_log_index                        = mariadb-relay.index
log_slave_updates                      = ON
gtid_strict_mode                       = OFF
columnstore_use_import_for_batchinsert = ALWAYS
server_id                              = {server_id}
"""


util_query="""
CREATE USER '{util_user}'@'127.0.0.1'
IDENTIFIED BY '{util_password}';

GRANT SELECT, PROCESS ON *.*
TO '{util_user}'@'127.0.0.1';
"""

repl_query="""
CREATE USER '{repl_user}'@'{slave_host}' IDENTIFIED BY '{repl_password}';

GRANT REPLICA MONITOR,
    REPLICATION REPLICA,
    REPLICATION REPLICA ADMIN,
    REPLICATION MASTER ADMIN
ON *.* TO '{repl_user}'@'{slave_host}';
"""

slave_replica_users_query="""
    STOP SLAVE;
    CHANGE MASTER TO
        MASTER_HOST='{master_host}',
        MASTER_USER='{repl_user}',
        MASTER_PASSWORD='{repl_password}',
        MASTER_USE_GTID=slave_pos;

    START SLAVE;
    STOP SLAVE;
    RESET SLAVE;
    START SLAVE;
"""


engineering_repo = """
[Columnstore-Internal-Testing]
name = Columnstore-Internal-Testing
baseurl = {mcs_baseurl}
gpgcheck = 0
enabled = 1
module_hotfixes = 1

[CMAPI-Internal-Testing]
name = CMAPI-Internal-Testing
baseurl = {cmapi_baseurl}
gpgcheck = 0
enabled = 1
module_hotfixes = 1"""