# Concept guide

Xbench uses a declarative approach. Everything (which includes cluster topology, instance parameters, workload parameters etc, etc) are define in yaml files. You can find all configuration yaml files in the `conf` directory. It is user responsibility to properly maintain configuration files.

For most of the use cases you will not need to touch the source (python) code.
The only reason when you need change the code is when you want to introduce a new type of workload or new database.

## Terminology

`cluster` - cluster is a combination of the compute resources such as driver(s), backend(s), and proxy(ies).

`cluster file` - a YAML file in the $HOME/.xbench/clusters directory, which contains all resources has been provisioned. This file is auto-generated, do not modify this file. If you lost your cluster file you still will be able to deprovision the cluster using `force` mode.

`topology` or `topo` - a map, which shows how drivers connect to proxy and/or backends. During the `provisioning` process Xbench verifies that `implementation` contains all details for each component listed in `topo`.

`implementation` or `impl` -

`environment` - Xbench allows to provision a single cluster across multiple clouds, for example: driver in AWS and backend in SkySQL. Access pattern and API for different clouds are so different, that to be able to still managed such configuration Xbench internally creates `environments`.

`driver` - a standalone machine (EC2 instance as an example) were we place requested benchmark (sysbench or benchbase as example). This machine run only workload code and doesn't have any proxies or backends.

`proxy` - a proxy between driver and backend. Currently only Maxscale is supported

`backend` - any supported database, MariaDB as en example. Any backend has corresponding yaml file, mariadb.yaml for MariaDB.

`benchmark` - a benchmark tool/binary, such as sysbench or TPCC. Each benchmark has it's own configuration file. For sysbench it is `sysbench.yaml`

`workload` - set of parameters for running certain `benchmark`. These parameters defined in the `workload.yaml`

`artifact directory` - a directory where results of running workload stored. By default this is a same directory as log directory.

`vault` - Xbench stores all the secrets such as passwords or API keys in the $HOME/.xbench/vault.yaml. This is user responsibility to keep it secure.

## Topology (topo.yaml)

Choosing the right topology is the most important step in planning a future test.

In the example below cluster will have:

- one (or more) identical drivers
- one (ore more) identical proxies
- one (or more) identical backends

Example 1:

```yaml
default_xpand:
  driver:
    proxy:
      - backend

```

The above topo can be represented as shown below:

```

cluster
└── driver
    └── proxy
        └── backend

```

Example 2:

<pre>

special_xpand:
  driver: # Zone a
    proxy1: # Zone a
      - backend1 # Zone a
      - backend2 # Zone b
      - backend3 # Zone c
    proxy2: # Zone b
      - backend1
      - backend2
      - backend3
</pre>

## Implementation (impl.yaml)

Implementation contains details required for provisioning and installation:

1. Cloud name and region
2. for every component (driver, proxy, backend):

    - zone information
    - instance type
    - operating system
    - network type
    - storage type
    - reference to the Python class which responsible for the installation
