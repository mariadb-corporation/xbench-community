# Demo scenario for Xbench

Before the demo - switch on VPN!!

Clusters to run

Screen 1:

```shell

# MariaDB aws
CLUSTER=aws-mariadb
x r --topo single_node  --impl aws_mariadb  --benchmark sysbench  --workload oltp_read_write

# MariaDB arch
xbench.sh run  --cluster aws-mariadb  --topo single_node  --impl aws_mariadb_arch  --benchmark sysbench  --workload oltp_read_write

# MariaDB GCP
x  r  --cluster gcp-mariadb  --topo single_node  --impl gcp_mariadb  --benchmark sysbench  --workload oltp_read_write

#Xpand
CLUSTER=aws-xpand
x r  --cluster aws-xpand   --topo xpand_performance   --impl aws_xpand --benchmark sysbench  --workload oltp_read_write


# Posgtres

xbench.sh run  --cluster aws-postgres  --topo single_node  --impl aws_postgres  --benchmark sysbench  --workload oltp_read_write

```

Screen 2

```shell

#SkySQL
xbench.sh run --cluster aws-sky --topo sky --impl aws_driver,aws_sky_xpand --benchmark sysbench --workload oltp_read_write


# SkySQL V2.0
xbench.sh p --cluster aws-sky2-xgres --topo sky --impl aws_east_driver,skysql_xgres --log-level DEBUG
xbench.sh run --cluster aws-sky2 --topo sky --impl aws_driver,aws_sky2_xpand --benchmark sysbench --workload oltp_read_write
xbench.sh run --cluster aws-sky2 --topo sky --impl aws_driver,aws_sky2_mariadb --benchmark sysbench --workload oltp_read_write


# Aurora MySQL
xbench.sh run --cluster aws-aurora --topo single_node --impl aws_aurora,aws_driver --benchmark sysbench --workload oltp_read_write

```

Important Links:

Grafana dashboard

AWS:
<https://it-admin-aws-sso.awsapps.com/start#/>

GCP:
<https://console.cloud.google.com/compute/instances?project=mariadb-clustrix>

Sky:
<https://cloud.mariadb.com/skysql?id=services>

Using team login account and backup codes

Iterm 2

function title {
  PROMPT_COMMAND="echo -ne \"\033]0;$1 \007\""
  printf "\e]1337;SetBadgeFormat=%s\a"   $(echo -n "\(session.name)" | base64)
  }
dv:~$ title HEY

iterm2 Hot Keys

Switch between tabs
CTRL + arrow

Splitting

Split Window Vertically (same profile) ⌘ + D
Split Window Horizontally (same profile) ⌘ + Shift + D (mnemonic: shift is a wide horizontal key)

Zoom one panel
⌘ + Shift + Enter (use with fullscreen to temp fullscreen a pane!)

Resize panel CTRL + ⌘  arrow

## Recording

Press Command + Shift + 5

##

Dashboards
Xpand without WIP
<http://35.91.94.4:3000/d/xpand2/xpand-stats?orgId=1&from=1661805918696&to=1661826138318>

mysql-exporter-quickstart-and-dashboard
<http://35.91.94.4:3000/d/549c2bf8936f7767ea6ac47c47b00f2a/mysql-exporter-quickstart-and-dashboard?orgId=1&from=1661879448165&to=1661882394473>

node exporter
<http://35.91.94.4:3000/d/NE2/node-exporter?orgId=1&refresh=1m&var-DS_PROMETHEUS=Prometheus&var-job=central_metrics_poll&var-cluster=mariadb-dashboard&var-node=backend-0&var-diskdevices=%5Ba-z%5D%2B%7Cnvme%5B0-9%5D%2Bn%5B0-9%5D%2B%7Cmmcblk%5B0-9%5D%2B>

<http://35.91.94.4:3000/d/000000039/postgresql-database?orgId=1&refresh=10s&var-interval=$__auto_interval_interval&var-cluster=aws-postgres&var-namespace=&var-release=&var-name=&var-datname=All&var-mode=All&from=now-6h&to=now>
