# How To guide

## Connect to the provisioned cluster

### From your laptop

You can use shell helpers s.sh (shell) and m.sh(mariadb) to connect to the host and db:

```shell
export CLUSTER='your_cluster_name'
$XBENCH_HOME/bin/s.sh <host>
```

where 'host' is a logical name from your $HOME/.xbench/clusters/'your_cluster_name'.yaml file, typically this is driver_0, backend_0 etc..

```shell
export CLUSTER='your_cluster_name'
$XBENCH_HOME/bin/m.sh backend_0
```

### From the driver

In order to connect to the DB from the driver you need to get a connection properties from your cluster file: $HOME/.xbench/clusters/'your_cluster_name'.yaml. Check for bt property:

```yaml
bt:
  host: 172.31.24.26,172.31.25.245,172.31.23.133
  user: xbench
  database: sysbench
  port: 3306
```

## Run benchbase tpc-c workload

Benchbase supports a lot of workloads, including tpc-c, tpc-h. In the example below you will see how to run tpcc.

First of all, in impl.yaml file you need to request benchbase to be installed on all your drivers by specifying:

```yaml
driver:
    klass: driver.BaseDriver # must be class reference
    klass_config_label: benchbase # For Driver this is reference to benchmarks to install
```

Secondly, check benchmark parameters in `workload.yml` as shown below:

```yaml
benchbase:  # this is benchmark parameter for xbench.sh
  defaults:
    klass: benchmark.BenchbaseRunner # do not change this.
    scale: 1000 # this is number of warehouses
    batchsize: 128
    randomseed: 1234567
    time: 300
    repeats: 1
    post_data_load: True # call backend specific code after data load
    pre_workload_run: True # call backend specific code before each full repeat starts
    pre_thread_run: True # call backend specific code before each thread
  workloads:
    tpcc: # this is a workload parameter for xbench.sh
      bench: tpcc # this is tpcc workload
      terminals: [90, 180, 270, 360, 450] # must be a int or list
      time: 360
      warmup: 60
```

Parameters above are merging into `benchbase_tpcc_config.xml` template file. Note, that inside template file there are few conditional section like

```yaml
{% if product == 'mariadb' %}
```

`product` is something that backend class should specify. Finally you run the benchmark as:

```shell
./bin/xbench.sh w --cluster benchbase_pg --workload tpcc --benchmark benchbase

```
