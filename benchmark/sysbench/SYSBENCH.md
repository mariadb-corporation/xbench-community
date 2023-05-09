# Sysbench guide

## Installation

Download Sysbench 1.x as:

```bash
curl -s https://packagecloud.io/install/repositories/akopytov/sysbench/script.rpm.sh | sudo bash
yum -y install sysbench
```

## Workload scripts

The lua scripts are located under /usr/share/sysbench. They can used right away

```bash
sysbench /usr/local/share/sysbench/oltp_read_only.lua help
```

Full example would be:

```bash
/usr/local/share/sysbench/oltp_read_write.lua --point-selects=9 --range-selects=false --index-updates=0 --non-index-updates=1 --delete-inserts=0 --rand-type=uniform --report-interval=10 --tables=10 --table-size=1000000 --time=120 --histogram --mysql-db=sysbench --db-driver=mysql --mysql-host=yang02f --mysql-user=cbench --mysql-password=Ma49DB4F#+Pa13w0rd --mysql-port=3306 --threads=8 --rand-seed=2469134 run
```

## Build sysbench from the source

Commands below applies to the CentOS 7. Sysbench will be linked with MariaDB libraries (not MySQL).

Install operating system support packages:

```bash
yum -y install make automake libtool pkgconfig libaio-devel
yum -y install openssl-devel zlib-devel
```

Setup MariaDB repo:

```bash
curl -sS https://downloads.mariadb.com/MariaDB/mariadb_repo_setup | sudo bash
sudo yum -y install MariaDB-shared MariaDB-devel    # this will also install MariaDB-client MariaDB-common
```

Clone and build sysbench:

```bash
git clone https://github.com/akopytov/sysbench
cd sysbench
./autogen.sh
./configure  --with-mysql-includes=/usr/include/mysql   --with-mysql-libs=/usr/lib64/ --disable-shared --enable-static

make
sudo make install
sysbench --version
```

## UTF8 Support

Sysbench is linked with libmysqlclient.so and uses whatever this client library uses as default.
With libmariadb.so another library exists that is compatible at call level. The sysbench
in custrixbench (under .../clustrixbench/tools/sysbench1.1/) is linked with ''that'' library
which also solves a problem with SSL.
