# Xbench

Xbench is a CLI for running performance benchmarks against various databases in the cloud.

## Support status

Currently Xbench supports:

- Clouds:
  - AWS EC2
  - AWS Aurora
  - AWS S3
  - SkySQL (Xpand and MariaDB)
  - Sproutsys (colo datacenter)

- Database:
  - MariaDB Enterprise Server
  - MariaDB Community Server
  - MariaDB Columnstore
  - Xpand
  - Aurora MySQL and PostgreSQL
  - PostgresSQL
  - TiDB
  - Any MySQL or Postgres compatible database provisioned by you

- Benchmarks:
  - [Sysbench](https://github.com/mariadb-corporation/sysbench-bin) OLTP
  - [Sysbench](https://github.com/mariadb-corporation/sysbench-bin) TPC-C
  - [Benchbase](https://github.com/cmu-db/benchbase) (A [fork](https://github.com/mariadb-corporation/benchbase) is currently used)
  - [HammerDB](https://github.com/TPC-Council/HammerDB) (A [fork](https://github.com/mariadb-corporation/HammerDB) is currently used)
- Custom benchmark
  - [Xpand-Locust](https://github.com/mariadb-corporation/xpand-locust) (installation only)

## Installation

Please choose a directory where you would like to install Xbench, typically this is $HOME/xbench. In this guide we call this directory `XBENCH_HOME`.

```shell
cd $HOME
git clone -b develop https://github.com/mariadb-corporation/xbench.git
XBENCH_HOME=`pwd`/xbench
```

Please add PATH to the to your `.bash_profile`:

```shell
XBENCH_HOME=$HOME/xbench
PATH=$XBENCH_HOME/bin:$PATH
PYTHONPATH=${XBENCH_HOME}
export PATH PYTHONPATH XBENCH_HOME
```

## Requirements

### Python

We have tested out code with Python 3.9.5. Please install it using [pyenv](https://github.com/pyenv/pyenv) (recommend) or virtual environment as shown below:

```bash
apt install python3.9-venv
python3.9 -m venv venv1
source venv1/bin/activate
```

Python dependencies are listed in [requirements.txt](requirements.txt) (for runtime environment) and [requirements_dev.txt](requirements_dev.txt) (for dev environment).

```shell
cd $XBENCH_HOME
pip3.9 install -r requirements.txt     # for dev or production
pip3.9 install -r requirements_dev.txt # for dev environment only
```

### Other dependencies

[aws cli version 2](https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html)

[Google Cloud CLI v412 or later](https://cloud.google.com/sdk/docs/install)

- When initializing, `gcloud config set project PROJECT_ID` is **optional**. `GcpCli` reads the `gcp_project_id` setting from `cloud.yaml` and adds it to each gcloud command automatically: `gcloud --project <gcp_project_id>`.
- `cloud.yaml` shall have the `service_account_file` for the `gcp` cloud defined and the JSON file must exist for `GcpCli.authorize_service_account()` to succeed, e.g.:

  ```yaml
  gcp:
    ...
    service_account_file: ENV['HOME']/.xbench/mariadb-clustrix-xbench.json
  ```

- In order to upgrade gcloud run `gcloud components update --version=412.0.0`

[jq-1.6](https://stedolan.github.io/jq/download/)

[yq](https://github.com/mikefarah/yq/) version 4.25.1

Directory belows contains secrets (AWS keys, passwords, pem files):

```shell
$HOME/.xbench  # You need to obtain this directory separately
```

You will need a vault.yaml in the above mentioned directory to run xbench.

### Vault

In order to use Xbench you need to obtain (or create) the vault (vault.yaml) and pem files.

Here is the structure of directories you supposed to create:

```shell
ls -la $HOME/.xbench
total 40
-rw-r--r--    1 user  group    61 Sep 15  2022 xbench_options
-rw-r--r--@   1 user  group  6253 Apr  5 12:24 vault.yaml  # Main secret store
drwxr-xr-x    9 user  group   288 Feb 13 13:31 pem      # PEM files to access remote machines
drwxr-xr-x  123 user  group  3936 Apr 26 14:24 logs
drwxr-xr-x   59 user  group  1888 Apr 26 14:24 clusters # all your clusters
drwxr-xr-x    5 user  group   160 Jun 13  2022 certs   # SSL certificates
```

Refer to the [Security](#security) section for an example vault file.

### Known issues

if you plan to use AWS based cluster and had aws cli utility configuration before please make use:

1. Unset AWS_PROFILE
2. remove [default] section from ~/.aws/credentials
3. Check [others variables](https://docs.aws.amazon.com/cli/latest/userguide/cli-configure-envvars.html) you might have set

## Developer's guide

See [DEV_GUIDE.md](DEV_GUIDE.md).

## Concept guide

See [CONCEPT_GUIDE.md](CONCEPT_GUIDE.md).

## Typical workflow

A typical workflow includes 3 commands:

- **Provision**: provision and configure required amount of resources in the requests cloud. Parameters:
  - topology (example: driver-proxy-database)
  - implementation strategy (which includes cloud and required resources. examples: aws and 3 m5d.8xlarge instances)
- **Workload**: run the benchmark (example: sysbench). Parameter: workload (example: 9010)
- **De-provision**: tear down provisioned resources

It is also possible to run all three workflow at once using the **run** command.

## Command-line interface

```shell
~$ cd $XBENCH_HOME
[xbench]$ ./bin/xbench.sh --help
usage: xb.py [-h] {provision,p,workload,w,deprovision,d,run,r,report} ...

Xbench - Performance Testing Framework

optional arguments:
  -h, --help            show this help message and exit

Commands:
  {provision,p,workload,w,deprovision,d,run,r}
    provision (p)       Provision cluster [configure, make, test, install, clean, all]
    workload (w)        Run benchmark against cluster [test, prepare, run, all]
    deprovision (d)     Deprovision all instances in cluster
    report              Plot latency-throughput curve for the workload
    run (r)             Run end-to-end workflow, e.g. provision -> workload -> deprovision -> report
```

The following table provides a summary of the supported command-line arguments by command:

| Arguments || Commands ||||||
| --- | :---: | :---: | :---: | :---: | :---: |  :---: | :---: |
| **Name** | **IsRequired** | `provision` | `workload` | `deprovision` | `run` | `report` | `start/stop`
| `artifact-dir` |  |  | &#9745; |  | &#9745; |  |
| `benchmark` | &#9745; |  | &#9745; |  | &#9745; | &#9745; |
| `cluster` | &#9745; | &#9745; | &#9745; | &#9745; | &#9745; | &#9745; | &#9745; |
| `dry-run` |  | &#9745; | &#9745; | &#9745; | &#9745; |
| `force` |  | &#9745; |  | &#9745; | &#9745; |
| `impl` | &#9745; | &#9745; |  |  | &#9745; |
| `log-dir` |  | &#9745; | &#9745; | &#9745; | &#9745; | | &#9745; |
| `log-level` |  | &#9745; | &#9745; | &#9745; | &#9745; | | &#9745; |
| `step` |  | &#9745; | &#9745; |  |  |
| `topo` | &#9745; | &#9745; |  |  | &#9745; |
| `workload` | &#9745; |  | &#9745; |  | &#9745; |
| `tag` |  |  | &#9745; |  | &#9745; |
| `cloud` |  |  |  | &#9745; |  |
| `region` |  |  |  | &#9745; |  |
| `notebook-name` |  |  |  |  |  | &#9745; |
| `notebook-title` |  |  |  |  |  | &#9745; |

Use the `--help` option to view all arguments and their available forms.

```shell
# Run in $XBENCH_HOME
$ xbench.sh provision --help
```

To get all available options and steps for individual commands run `xbench.sh` without arguments:

```shell
xbench.sh
```

## Examples

### Basic usage

**Note**: the `--cluster` or `-c` parameter value `aws-mariadb` is just an example. Set the cluster name to a unique value when testing to avoid collisions.

E.g. for development purposes use `--cluster <your_name>_cluster` or `-c <your_name>_cluster`

The simplest way to run xbench end-to-end is to use the following command (which will install MariaDB community edition in the AWS):

```shell
xbench.sh run \
  --cluster aws-mariadb \
  --topo single_node \
  --impl aws_mariadb \
  --benchmark sysbench \
  --workload oltp_read_write \
  --log-dir /tmp \
  --artifact-dir /tmp \
  --log-level INFO
```

Same MariaDB on GCP:

```shell
xbench.sh run  \
--cluster gcp-mariadb
--topo single_node
--impl gcp_mariadb
--benchmark sysbench
--workload oltp_read_write
--log-dir /tmp \
--artifact-dir /tmp \
--log-level INFO
```

The very similar way you could install PostgreSQL (note the difference in `--impl` parameter, though):

```shell
xbench.sh run \
  --cluster aws-postgres \
  --topo single_node \
  --impl aws_postgres \
  --benchmark sysbench \
  --workload oltp_read_write \
  --log-dir /tmp \
  --artifact-dir /tmp \
  --log-level INFO
```

Each command-line argument and command has a shorthand form. For example, the previous command could also be run like:

```shell
xbench.sh r \
  -c itest-cluster \
  -t single_node \
  -i aws_mariadb \
  -b sysbench \
  -w oltp_read_write
  -o /tmp \
  -a /tmp
  -l INFO \

```

If you want to test Xpand (COLO VPN required) with Maxscale  use the following:

```shell
xbench.sh run \
  --cluster aws-xpand \
  --topo xpand_performance \
  --impl aws_xpand \
  --benchmark sysbench \
  --workload oltp_read_write \
  --log-dir /tmp \
  --artifact-dir /tmp \
  --log-level INFO
```

To deploy and run benchmarks in the Sproutsys Colo, use the following:

```shell
xbench.sh provision \
  --cluster my-colo-deployment \
  --topo itest \
  --impl itest_colo \
  --log-level INFO \
  --log-dir /tmp
```

Or a full end-to-end run:

```shell
xbench.sh run \
  --cluster my-colo-deployment \
  --topo itest \
  --impl itest_colo \
  --benchmark sysbench \
  --workload 9010 \
  --log-dir /tmp \
  --artifact-dir /tmp \
  --log-level INFO
```

The run command will do:

1. Provision the nodes in selected cloud
2. Run sysbench using "oltp_read_write" workload
3. Deprovision the nodes

If you want you want to run each of 3 commands separately see below:

- [Provisioning](#provisioning)
- [Run workload](#run-workload)
- [De-provisioning](#de-provisioning)

You can customize any implementation parameters using the following syntax: --component.name=value

```shell
xbench.sh p \
  -c itest-cluster \
  -t xpand_performance \
  -i aws_xpand \
  -o /tmp \
  -a /tmp \
  -l INFO \
  --backend.instance_type=m5d.4xlarge \
  --driver.zone=us-west-2c \
  --backend.storage.size=500
```

Backend configuration parameters (which listed in "backend".yaml for each backend, conf/xpand.yaml as an example) can be override using `--backend.config.parameter` syntax, for example `--backend.config.build=17974` for Xpand. If you want to set server variables for Xpand you could specify `backend.config.globals.<variable>=<value>`

Same idea applies to the workload parameters (see running workload section below)

## SSL support

Xbench currently offers limited SSL support for MariaDB/MySQL only.
Before run test with SSL support make sure you have certificates locally.

To enable SSL you have to add `ssl` dictionary to your `db` property in `mariadb.yaml` (see community_ssl as full example) and specify 3 keys as shown below:

```yaml
ssl:
      ssl_ca: ENV['HOME']/.xbench/certs/ca.pem
      ssl_cert: ENV['HOME']/.xbench/certs/server-cert.pem
      ssl_key: ENV['HOME']/.xbench/certs/server-key.pem
```

Xbench will copy these certificates to the driver and server and enable server for using it.

### Using Xbench in multicloud environment

Xbench natively supports multicloud environment, for example:
Setup 1:

1. Backend in SkySQL
2. Driver in AWS

Setup 2:

1. Backend in AWS Aurora
2. Driver in AWS region

To be able to create a cluster across multiple clouds you need to create 2 or more implementation strategies. Each implementation can describe only a single cloud. Then you could specify multiple implementations separated by ","  when running Xbench:

SkySQL Xpand example:

```shell
xbench.sh run --cluster aws-sky --topo itest_sky --impl skysql_driver,skysql_test --benchmark sysbench --workload itest --log-dir /tmp --artifact-dir /tmp
```

Aurora example:

```shell
xbench.sh run --cluster itest-aurora --topo itest_aurora --impl itest_aurora,only_driver --benchmark sysbench --workload itest --log-dir /tmp --artifact-dir /tmp --log-level INFO
```

Columnstore sample:

For new we have two committed topologies in topo.yaml

- columnstore_s3 - three machines cluster with S3 storage
- columnstore_hdd - three machines cluster with hdd storage
Any other topologies should be added manually to topo.yaml, having whis two as example.

We have this sections in impl.yaml. They all points to corresponding section in columnstore.yaml

- cs_develop. Install cluster from latest Drone Build. Points to 'latest' section in columnstore.yaml
  Seeng this latest section, params are
- branch: develop # possible any branch, builded on Drone
- build: latest # possible variants: custom-NNN, cron-NNN, pull_request-NNNN, latest
- server_version: "10.6-enterprise" # possible variants: 10.9, 10.6-enterprise
   only this one is ready for S3 topologies now. See impl.yaml for details, comparing this with others
so

```shell
./bin/xbench.sh p --cluster=detravi-cluster \
                  --topo=columnstore_hdd  \
                  --impl=cs_develop
                  --log-dir=/tmp
                  --artifact-dir=/tmp
                  --log-level DEBUG
```

will install latest Drone build from develop to cluster and

```shell
./bin/xbench.sh p --cluster=detravi-cluster
                  --topo=columnstore_hdd
                  --impl=cs_develop
                  --log-dir=/tmp
                  --artifact-dir=/tmp
                  --log-level DEBUG
                  --backend.config.build=pull_request_5932
```

will install <https://cspkg.s3.amazonaws.com/index.html?prefix=develop/pull_request/5932/10.6-enterprise/amd64/rockylinux8/>

```shell
./bin/xbench.sh p --cluster=detravi-cluster
                  --topo=columnstore_hdd
                  --impl=cs_develop
                  --log-dir=/tmp
                  --artifact-dir=/tmp
                  --log-level DEBUG
                  --backend.config.server_version=10.9
```

will use 10.9 server instead of 10.6 enterprise

- cs_develop_6 - Install cluster from develop-6 build, points to develop-6 section in columnstore.yaml
  the same as cs_develop, but uses develop-6 branch Drone builds as default

- cs_enterprise - Install cluster from Enterprise Repo, points to enterprise section in columnstore.yaml
  Uses enterprise repo to install cluster
- cs_jenkins - Install cluster from jenkins build, points to jenkins section in columnstore.yaml
  has two special params

    -- mcs_baseurl: VAULT['mcs-jenkins-baseurl']
      because of credentials this is stored in

    ```shell
    $ cat ~/.xbench/vault.yaml
    mcs-jenkins-baseurl: https://<user>:<password>@es-repo.mariadb.net/jenkins/ENTERPRISE/bb-10.6.9-5-cs-22.08.4-1/00008abf9c047131eff915b84299a931e4a93794/RPMS/rhel-8
    ```

    -- cmapi_baseurl: "https://cspkg.s3.amazonaws.com/cmapi/develop/pull_request/788/amd64"

    this two params can be overriden with
        --backend.config.mcs_baseurl
    and --backend.config.cmapi_baseurl
    one for engine repo, second for cmapi repo.
    for example

```shell
./bin/xbench.sh p --cluster=detravi-cluster
                  --topo=columnstore_hdd
                  --impl=cs_jenkins
                  --log-dir=/tmp
                  --artifact-dir=/tmp
                  --log-level DEBUG
                  --backend.config.mcs_baseurl=https://<user>:<password>@es-repo.mariadb.net/jenkins/ENTERPRISE/bb-10.6.9-5-cs-22.08.4-1/0008abf9c047131eff915b84299a931e4a93794/RPMS/rhel-8
                  --backend.config.cmapi_baseurl=https://cspkg.s3.amazonaws.com/cmapi/develop/pull_request/788/amd6
```

- cs_develop_arm Install cluster from develop on arm machines
  main params here stored in impl section
    -- instance_type: a1.xlarge
    -- os_type: Rocky8
    -- arch : aarch64
    they can be overriden like

  ```--backend.instance_type=a1.small```

```shell
./bin/xbench.sh p --cluster=detravi-cluster --topo=columnstore_s3 --impl=cs_develop --log-dir=/tmp --artifact-dir=/tmp --log-level DEBUG
```

for object S3 storage and develop latest build

```shell
./bin/xbench.sh p --cluster=detravi-cluster --topo=columnstore_hdd --impl=cs_develop-6 --log-dir=/tmp --artifact-dir=/tmp --log-level DEBUG
```

for local storage and develop-6 latest build

### Provisioning

```shell
xbench.sh p \
  -l INFO \           # LOG_LEVEL
  -o /tmp \           # LOG_DIR
  -c itest-cluster \  # CLUSTER
  -t itest \          # TOPO
  -i itest \          # IMPL
```

The provision command will run through all steps, except clean.

If you want to run a specific step, use the `--step` (`-s`) option:

```shell
xbench.sh p \
  -l INFO \           # LOG_LEVEL
  -o /tmp \           # LOG_DIR
  -c itest-cluster \  # CLUSTER
  -t itest \          # TOPO
  -i itest \          # IMPL
  -s make             # STEP
```

Possible values for `step` are:

- configure: configures cluster
- allocate:  allocate instances in the Cloud
- test: run self test
- make: prepare instance
- install: installs software on instances.
- clean:  uninstall software on instances
- all: run all the above but clean

Once cluster has been provisioned you will find corresponding yaml file in the $HOME/.xbench/clusters/`your cluster`.yaml. Wee called it `cluster file`. Please do not edit it manually: if you need to make a change, like adding nodes, you need to deprovision the current cluster and start over again.

### Run workload

```shell
xbench.sh w \
  -l INFO \
  -o /tmp \
  -c itest-cluster \
  -t itest \
  -i itest \
  -b sysbench \
  -w 9010
```

The workload command will run through all the steps.

If you want to run a specific step, use the `--step` (`-s`) option:

```shell
xbench.sh w \
  -l INFO \
  -o /tmp \
  -c itest-cluster \
  -t itest \
  -i itest \
  -b sysbench \
  -w 9010 \
  -s prepare
```

Possible values for `step` are:

- test: run connectivity test
- prepare: create schemas and load data.
- run: run benchmark
- all: run all the above
- backup: backup database, using the following notation: benchmark_workload_scale_tag
- restore: restore database

Workload parameters can be overridden using `workload` prefix:

```shell
xbench.sh w \
  -l INFO \
  -o /tmp \
  -c itest-cluster \
  -t itest \
  -i itest \
  -b sysbench \
  -w 9010 \
  --workload.threads=[8,16,32] \
  --workload.repeats=2
```

For some special cases you may want to override the way benchmark/driver connecting to the database.
with a syntax like `--bt.<param>=<value>` you can do it for workload run and prepare. Please find the list of `param` below:

```shell
host
user
password
database
port
ssl
dialect
product
connect_timeout
read_timeout
```

`ssl` parameter is a dictionary with keys `ssl_ca`, `ssl_cert`, `ssl_key` and can be specified as shown below:

`--bt.ssl='{"ssl_ca":"~/Downloads/skysql_chain_2022.pem"}'`

Backup and restore examples:

```shell
# Backup
xbench.sh w \
-b benchbase \
-w tpcc_1k \
--tag=my_tag \
--step=backup

# Restore
xbench.sh w \
-b benchbase \
-w tpcc_1k \
--tag=my_tag \
--step=restore
```

Please note that `--tag` is an optional. If you are experimenting with schema or storage parameters it is better tag you backup and not override the default one.

### De-provisioning

```shell
xbench.sh d -l INFO -o /tmp -c itest-cluster
```

The cluster yaml file is backed up to the `artifact_dir` and deleted from the `ENV['HOME']/.xbench/clusters` directory.
If things went south you might want to release allocated hardware using the nuke `--force` (`-f`) option:

```shell
xbench.sh deprovision --cluster itest-cluster --force --cloud aws --region us-east-1-PerformanceEngineering
```

`cloud` and `region` above are entries in the `cloud.yaml`. Please note that nuke doesn't required cluster file. Therefore you can deprovision any cluster, even not yours. This also means that the cluster file will not be deleted after nuke so it must be manually deleted if the cluster is to be re-provisioned. In addition, regular provisioning works for multi-region clusters, while force can work only in one cloud/region at a time.

### Reporting

If you use `run` command you are getting a notebook with results and plot for free. You still may want to put multiple graphs on the same plot user `reporting` command:

```shell
 xbench.sh report -c aws-mariadb -b sysbench --notebook-name mynote --notebook-title mytitle
```

This command will scan all results under your --log-dir and place them together for comparison.

## Advanced usage

### Starting and stopping your cluster

Sometimes, you want to assess the results after you run your workload. Sometimes it takes hours and even days.  Deleting your cluster is not always an option because creating a database could take a very long time.  Now you could just stop your cluster without losing anything (that is if you haven't used local SSD/NVMe)

```shell
x stop
# Once you are ready to resume your command
x start
```

Start/Stop command will change `state` filed in cluster.yaml. This is a guardrail against trying to stop or start a cluster twice. You can delete you cluster
no matter which state is it.

### Command line options file

If you get tired from specifying the same `xbench.sh` parameters (`log-dir` and `log-level`)  you can put them into `$HOME/.xbench/xbench_options`. You still will be able to override them.

### Shell profile and CLUSTER variable

You can make your life a bit easier with some bash/zsh profile settings:

```shell
alias x=xbench.sh
export PS1='\[\033[01;32m\]$CLUSTER:\[\033[01;34m\]\w\[\033[00m\]\$ '
```

Now if you choose to set environment variable `CLUSTER` (in the example below `CLUSTER=dsv-mariadb`), you will see a nice prompt:

```shell
dsv-mariadb:~/GitHub/xbench$
```

and you don't need to specify `--cluster` anymore for xbench commands! For example, your command become:

```shell
x p --topo itest -impl itest # Provision the cluster $CLUSTER
x d   # Delete the cluster $CLUSTER
```

### External commands

Xbench supports a few commands which simplifies your life:

#### ls command

Prints all cluster members and their IPs.
Format: "member':'public ip': 'private ip'

```shell
x ls
state: ready
cluster
└── driver-0
    └── backend-0
backend-0:35.91.65.135,172.31.16.146
driver-0:52.39.218.114,172.31.17.216
```

#### ssh command

Allow to get an interactive prompt or run ssh command on the cluster

General syntax is `x ssh <cluster member> ["command"]` where the `command` argument is an optional. Make sure to use the proper `cluster_member` from the `ls` command above.

```shell
x ssh backend-0 # will open an interactive ssh session for you
x ssh backend-0 "pwd;date;ls -la" # will run these commands
x ssh backend-0 <<EOF
date
pwd
EOF # Yet another way to run commands
```

#### send and recv command

`send` and `recv` commands allow you to send or received files (or directories) from a cluster member using `scp`

```shell
# sending local file to the cluster member
x send backend-0 /tmp/my.cnf /data/mariadb/my.cnf # Send local file to the backend
# receiving remove file
x recv backend-0 /data/mariadb/logs/db.log /tmp # Receive remote file
# sending the local directory to the cluster member
x send backend-0 /tmp/my_dir /tmp/
```

#### sql command

SQL command allow you to execute an arbitrary sql command against your cluster.

Prerequisites for running `sql` command is to having `mariadb` and `psql` utilities installed locally. Xbench will run the appropriative utility for you based on `dialect` property of your `bt` in the cluster yaml file.

General syntax is `x sql <cluster member> ["sql"]` where the `sql` argument is an optional. Make sure to use the proper `cluster_member` from the `ls` command above.

```shell
x sql backend-0 # will open an interactive sql session for you
x sql backend-0 "select * from t" # will run these commands
x sql backend-0 << EOF
show tables;
select * from t;
EOF # Yet another way to run commands
```

### External Database

If Xbench doesn't have a backend class for database of your choice, you still can use Xbench for performance testing. Let's assume we have already provisioned  MySQL compatible database.
You need to use a normal topo and impl (with driver and backend), and here an example of how to define backend:

```yaml
backend:
    klass: backend.ExternalMysqlDB #  backend.ExternalXpand
    klass_config_label: skysql_xpand
    managed: False # do not ssh
    provisioned: False # do not provision
    count: 1
    network:
      public_ip: 127.0.0.1 # It could be passed in command line as backend.network.public_ip
      cloud_type: private_cloud # Driver will use public IP
```

Provisioning (note dns name of my external database):

```shell
x p --topo single_node --impl simple_external --backend.network.public_ip=dbpwf42247295.sysp0000.db1.skysql.net
```

Running the workload (note, that user, password, port have been specified):

```shell
x w --benchmark sysbench  --workload oltp_read_write  --bt.user=dbpwf42247295 --bt.password='mypass' --bt.port=3306
```

### Experimentation

If you need to run the same workload multiple times, changing something in the middle, please follow the [experiment pattern](experiments): basically, experiments provide you several primitives (shell functions) to write your scenario. In this [example](experiments/large_num_slices.sh) multiple workloads run with some alter tables in between.

Now you might wonder - if I run multiple workloads, how can I remember which one was with what setting? Here comes a tagging concept handy (--tag): you can tag each workload run, and this tag will appear on the final graph.

Best of all - now you can create a yaml file describing how you want to get you results plotted after an experiment is done:

```yaml
mode: detailed # "summary" will summary,csv, other value will load individual runs
title: "Slicing experiment"
annotation: "I am annotation"
color_palette: "Set2"
```

all you need to do is to call `report` function after the main experiment code.

### Using xb.py directly

xbench.sh just a shell wrapper around xb.py. Make sure you have properly set your environment as describe in the [installation](#installation) section. Now you can use directly xb.py with the same parameters as shown in this guide.

## Still have questions?

Check out our [HowTo](HowTo.md) guide.

## Security

Xbench provides two level of security:

1. Cloud based keys/secret file: in order to use Xbench you have to have specify cloud's secret keys.
2. IP based security - your IP address has to be whitelisted (highly recommend)

The passwords, keys, tokens, and licenses used in Xbench should be stored in the `vault_file` which is specified in `xbench_config.yaml`. This is a yaml file which can be referenced by other yaml files by using the syntax: `VAULT['key']`. An example vault file would look like the following:
```yaml
aws_access_key_id: <insert key id>
aws_secret_access_key: <insert secret>
xbench_db_password: <insert password>
```
With references to the AWS key and secret in `cloud.yaml` and the database password referenced in the backend yaml config file.

For whitelisting Xbench provides a special command `security` (or `s`)

```shell
# x security --action=ls|addip|delip --ip <ip address, default to local public ip> --cloud [cloud] --region [region from cloud.yaml]

# Check current list of allowed IPs. You can skip action=list as this is default option
x s --action=list --cloud aws --region us-west-2-PerformanceEngineering

# Add IP
x s --action=addip --ip=10.10.10.10 --cloud aws --region us-west-2-PerformanceEngineering

# Remove IP
x s --action=delip --ip=10.10.10.10 --cloud aws --region us-west-2-PerformanceEngineering
```

## Maintenance

We need to rotate pem files regularly:

```shell
cd $HOME/.xbench/pem
ssh-keygen -t rsa -m PEM -f xbench.pem -N ''
```

TODO: Define how to rotate AWS secrets

## Sandbox

If want to use xbench without dealing with dependencies, you can use vqc008d (Colo VPN is required):

```shell
ssh -l root vqc008d
cd $XBENCH_HOME
git pull
```

Run all examples as shown above. Please note that vqc008d uses xbench_options file and by default put all logs into `/data/performance/log/vqc008d-xbench`

That way other will be able to see your work.

### Running Jupyter server remotely

[Update Jupyter config](https://stackoverflow.com/questions/42848130/why-i-cant-access-remote-jupyter-notebook-server) (this has been done on vqc already)

Setting up remote access

```shell
jupyter notebook --generate-config
```

This will create the `$HOME/.jupyter/jupyter_notebook_config.py`

You'll need to uncomment and edit the lines in the generated config file

```shell
c.NotebookApp.allow_origin = '*'
c.NotebookApp.ip = '0.0.0.0'
```

```shell
export PYTHONPATH=$XBENCH_HOME
cd $XBENCH_HOME/notebooks
PYTHONPATH=../:$PYTHONPATH jupyter notebook --ip 0.0.0.0 --port 8888 --allow-root --no-browser
```

Please note in the console output something like that:

```shell
http://vqc008d.colo.sproutsys.com:8888/?token=
```

Please copy this into your local browser.
