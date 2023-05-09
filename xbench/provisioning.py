import os

from dacite import from_dict

from backend.exceptions import BackendException
from cloud import CloudException
from cloud.cloud_factory import CloudFactory
from cloud.ephemeral import EphemeralCloud
from cloud.virtual_storage import VirtualStorage
from common.common import save_dict_as_yaml, simple_dict_items
from compute import (
    Cluster,
    ClusterState,
    Environment,
    Node,
    NodeException,
    ShellSSHClientException,
    run_parallel,
    run_parallel_returning,
)
from compute.backend_target import BackendTarget
from driver import DriverException
from metrics.server import MetricsServer
from proxy.abstract_proxy import AbstractProxy

from .common import (
    extender,
    klass_instance_clean,
    klass_instance_configure,
    klass_instance_install,
)
from .exceptions import XbenchException
from .xbench import Xbench


class EnvironmentComponents:
    def __init__(
        self, name, cloud: str, cloud_klass: str, region: str, region_config: dict
    ):
        self.env = Environment(name, cloud, cloud_klass, region)
        self.region_config: dict = region_config
        self.components: dict[
            str, dict
        ] = {}  # list of all component, parameters with their de-normalized  params
        self.shared_storage: list[VirtualStorage] = []

    def add_component(self, name: str, params: dict):
        self.components[name] = params

    def get_component_params(self, name: str):
        return self.components.get(name, None)


class Provisioning(Xbench):
    """Main class to provision cluster in the cloud"""

    def __init__(
        self,
        cluster_name: str,
        topo: str,
        impl: str,
        artifact_dir: str,
        extra_impl_params: dict = {},
        dry_run: bool = False,
    ):
        super(Provisioning, self).__init__(cluster_name, dry_run)
        self.artifact_dir = f"{artifact_dir}/{cluster_name}"

        self.extra_impl_params = extra_impl_params

        # Class properties
        self.topo = topo
        self.impl = impl  # This can be comma separated string

        # The goal is to set up a Cluster object will all members
        self.cluster = None
        #
        self.envs: list[EnvironmentComponents] = self.build_envs()

        if self.extra_impl_params is not None:
            self.logger.info(
                f"Custom impl parameters were requested: {extra_impl_params}"
            )

    def build_envs(self) -> list[EnvironmentComponents]:
        """This build list of components across all implementations with all params which become later a VM"""

        envs = []
        # Loop over all implementations
        # impl represents an entry in impl.yaml (like itest)
        for i, impl in enumerate(self.impl.split(",")):

            # Load impl

            # Let's grab implementation params and top level defaults
            #     component_params = self.impl_yaml.get_key(
            #         root=self.impl, leaf=component, use_defaults=True
            #     )

            impl_params = self.load_impl(impl)

            #
            save_dict_as_yaml(
                os.path.join(self.artifact_dir, f"env_{i}_impl.yaml"), impl_params
            )

            # Enhance impl config - load common keys for given implementation strategy, cloud and region - labels from cloud.yaml
            common_impl_keys = simple_dict_items(impl_params)
            cloud = common_impl_keys.get("cloud", "")
            region = common_impl_keys.get("region", "")

            cloud_config = self.load_cloud(cloud)
            region_config = cloud_config.get(region, None)
            # Basic check if we've got a proper configuration
            if region_config is None:
                raise XbenchException(
                    f"There is a configuration issue with {region} for cloud: {cloud}"
                )

            cloud_klass = cloud_config.get("klass", "")

            # We going to use Envs in allocate down below
            env_c = EnvironmentComponents(
                f"env_{i}", cloud, cloud_klass, region, region_config
            )

            shared_storage = impl_params.get("shared_storage")
            if isinstance(shared_storage, list):
                for s in shared_storage:
                    vs = from_dict(data_class=VirtualStorage, data=s)
                    env_c.shared_storage.append(vs)

            for k, v in impl_params.items():  # 'driver1': {}
                if isinstance(v, dict):
                    this_component_params = (
                        common_impl_keys
                        | self.impl_yaml.get_key(
                            root=impl, leaf=k, use_defaults=True
                        )  # I need to apply defaults to nested level
                        | {"cluster_name": self.cluster_name}
                    )
                    env_c.add_component(
                        k,
                        extender(
                            this_component_params, self.extra_impl_params.get(k, {})
                        ),
                    )
            envs.append(env_c)

        return envs

    def get_component_params(self, name: str):
        """Get component params across all environments

        Args:
            name (str): component name
        """

        for env in self.envs:
            params = env.get_component_params(name)
            if params:
                return params

        raise XbenchException(f"Component {name} was not found")

    def configure(self):
        """Helper to build the final tree which takes into account count from impl"""

        self.logger.info(f"Configure the cluster {self.cluster_name}")
        for env_c in self.envs:
            cloud = CloudFactory().create_cloud_from_str(
                env_c.env.cloud, self.cluster_name, **env_c.region_config
            )
            if cloud.is_running():
                raise XbenchException(
                    f"Found resources already running in '{env_c.env.cloud}' for"
                    f" cluster '{self.cluster_name}'\nDeprovision the resources before"
                    " continuing."
                )

        # Load topology dict
        self.topo_config = self.load_topo(self.topo)

        # I can initiate a cluster object finally
        cluster = Cluster(
            cluster_name=self.cluster_name,
            topo=self.topo,
        )

        # Let's build the tree
        cluster.build_tree_from_dict(self.topo_config)
        self.logger.info("Cluster tree from topo")
        cluster.render_cluster_tree()

        # hash table to prevent component to be provisioned twice. database1 can be connected from two proxies (proxy1 and proxy2)
        component_hash = {}

        # Now let's go over topo cluster tree and build the implementation tree across all Environments
        for any_node in cluster.level_order_cluster_members():

            component = any_node.name  # driver1 for example

            # component, like database1 already has been provisioned
            if component_hash.get(component) is not None:
                any_node.name = component_hash.get(component)
                continue

            component_params = self.get_component_params(component)

            final_component_instances = []  # driver1_1, driver1_2
            # if component_params.get("managed") == True:
            for i in range(
                int(component_params.get("count"))
            ):  # int here is required in case param comes from command line as str
                name = f"{component}-{i}"  # new name for the component
                final_component_instances.append(name)
            # else:
            #    name = f"{component}-0"  # new name for the component
            #    final_component_instances.append(name)

            any_node.name = ",".join(final_component_instances)
            component_hash[component] = any_node.name

        # Print Final CLuster tree
        self.logger.info("Cluster tree after configure")
        cluster.render_cluster_tree()

        # Save Cluster
        cluster.topo_map = component_hash
        self.save_cluster(cluster)

    def node_configure(self, n: Node):
        """Configure node and it's storage after provisioning but before install"""
        n.configure(**self.xbench_config_instance.xbench_config)

    def allocate(self):
        """All real provision work happens here

        Raises:
            XbenchException: [description]
        """
        allocate_failed = False
        cluster = self.load_cluster()

        try:
            provisioned_clouds = (
                []
            )  # Hash map to memories in which clouds we have provisioned our resources

            for env_c in self.envs:
                cluster.envs.append(env_c.env)  # Record env name in the cluster config
                # I need EphemeralCloud just in case there are provisioned=False components
                # TODO - I need to pass extra params here
                ec = EphemeralCloud(
                    cluster_name=self.cluster_name,
                    **env_c.region_config,
                )

                # Loading cloud class dynamically
                cloud = CloudFactory().create_cloud_from_str(
                    env_c.env.cloud, self.cluster_name, **env_c.region_config
                )

                # Let's check that cluster is not running. This can't be overruled by any force (--force)
                if env_c.env.cloud not in provisioned_clouds:
                    provisioned_clouds.append(env_c.env.cloud)
                    if cloud.is_running():
                        raise XbenchException(
                            f"Cluster {self.cluster_name} already has been provisioned"
                        )
                else:
                    self.logger.warning(
                        "You are provisioning multiple environments in the same cloud."
                        " This doesn't make any sense"
                    )

                instances_to_launch = []
                nodes = []
                instances_to_fake = []
                ephemeral_nodes = []
                self.logger.info(f"Provisioning components for cloud {env_c.env.cloud}")
                # Here is the topo map. The problem topo doesn't know about env
                # topo_map:
                #    driver: driver_0,driver_1
                #    backend: backend_0
                for component, impl_names in cluster.topo_map.items():
                    for impl_name in impl_names.split(
                        ","
                    ):  # - driver: driver_0,driver_1
                        # Let's grab implementation params
                        component_params = env_c.get_component_params(component)

                        if (
                            component_params
                        ):  # Maybe this component in the difference env
                            component_params["env"] = env_c.env.name
                            component_params["role"] = cluster.remove_numbers(component)
                            component_params["name"] = impl_name  # cl1-driver0

                            # pem file
                            if component_params.get("key_file", None) is None:
                                component_params["key_file"] = env_c.region_config.get(
                                    "key_file", ""
                                )

                            if component_params.get("provisioned"):
                                instances_to_launch.append(component_params.copy())
                            else:
                                instances_to_fake.append(component_params.copy())

                # provision shared_storage
                cluster.shared_storage = cloud.launch_storage_instances(
                    env_c.shared_storage
                )

                if len(instances_to_launch) > 0:
                    nodes = cloud.launch_instances(instances_to_launch)
                    if nodes is None:
                        allocate_failed = True

                if len(instances_to_fake) > 0:
                    ephemeral_nodes = ec.launch_instances(instances_to_fake)
                for n in nodes + ephemeral_nodes:
                    if n is None:
                        allocate_failed = True
                    else:
                        cluster.add_member(n.vm.name, n)
                        cluster.state = ClusterState.allocated

                if allocate_failed:
                    cluster.state = ClusterState.failed
                    self.save_cluster(cluster)
                    raise XbenchException("One or more resources were not provisioned")
                else:
                    self.save_cluster(cluster)

        except (CloudException, NodeException) as e:
            raise XbenchException(e)

    def make(self):
        """Basic preparation of the node

        Raises:
            XbenchException: _description_
        """
        try:
            cluster = self.load_cluster()
            # One env in a time
            for env_c in self.envs:
                self.logger.info(f"Configure all nodes in environment {env_c.env.name}")
                region_config = env_c.region_config
                MetricsServer().initialize(**region_config.get("metric_server", {}))

                configure_args = [
                    n
                    for n in cluster.members.values()
                    if n.vm.managed and n.vm.env == env_c.env.name
                ]

                noop = lambda x: x
                run_parallel(configure_args, noop, self.node_configure)

        except (CloudException, NodeException) as e:
            raise XbenchException(e)

    def self_test(self):
        """Check than node is accessible

        Raises:
            XbenchException: [description]
        """
        self.logger.info("Checking ssh connectivity for all nodes..")
        try:
            cluster = self.load_cluster()
            for i, node in cluster.members.items():
                if node.vm.managed:
                    self.logger.debug(f"Waiting for {node.vm.name}")
                    node.run("cat /etc/system-release")
                    self.logger.debug(f"{node.vm.name} check passed")
            self.logger.info("All checks passed")

        except (NodeException, ShellSSHClientException) as e:
            raise XbenchException(e)

    def get_klass_instances(self, cluster) -> list:
        """This method should return ready-to-run instances

        Args:
            cluster (_type_): _description_
        """
        klass_instances: list = []
        for k in cluster.get_member_nodes_klasses():
            klass_instances.append((k[0])(k[1], **self.extra_impl_params))
        return klass_instances

    def install(self):
        """Install software to the node

        Raises:
            XbenchException: [description]
        """
        try:
            cluster = self.load_cluster()
            bt = None
            # We can configure components env by env only
            for env_c in self.envs:
                self.logger.info(
                    f"Configuring all components in environment {env_c.env.name}"
                )
                region_config = env_c.region_config
                MetricsServer().initialize(**region_config.get("metric_server", {}))

                configure_args = [
                    {
                        "klass": member.get("klass"),
                        "nodes": member.get("nodes"),
                        "name": member.get("name"),
                        **self.extra_impl_params,
                    }
                    for member in cluster.group_nodes_by_name().values()
                    if member.get("env") == env_c.env.name
                ]

                noop = lambda x: x
                run_parallel(configure_args, noop, klass_instance_configure)

            # We install components across all environments (Multi-region Xpand)
            self.logger.info(f"Installing all components")
            install_args = [
                {
                    "klass": member.get("klass"),
                    "nodes": member.get("nodes"),
                    "name": member.get("name"),
                    **self.extra_impl_params,
                }
                for member in cluster.group_nodes_by_name().values()
            ]

            completed_installs = run_parallel_returning(
                install_args, klass_instance_install
            )

            for name, res in completed_installs:
                if res is not None:
                    bt = res
                    # Let see if There is any proxy. The thing is then we have to replace bt
                    # Let's find any tree node
                    my_node = cluster.find_node_by_name(name)
                    for _, v in cluster.group_nodes_by_name().items():
                        # let's find parent
                        if v.get("name") == my_node.parent.name:
                            if issubclass(v.get("klass"), AbstractProxy):
                                klass_instance = v.get("klass")(v.get("nodes"), **self.extra_impl_params)
                                bt = klass_instance.post_install(bt)

            # Update cluster with BackendTarget
            if bt is None:
                self.logger.warning(
                    "Cluster does not have properly configured backend target"
                )
                bt = BackendTarget(
                    host="127.0.0.1",
                    user="user",
                    password="no value",
                    database="no_value",
                    port=0,
                )
            cluster.bt = bt
            cluster.state = ClusterState.ready
            self.save_cluster(cluster)
        except ValueError as e:
            raise XbenchException(
                f"{e}. Please check that klass in the form module.class"
            )
        except (
            NodeException,
            ShellSSHClientException,
            DriverException,
            BackendException,
        ) as e:
            raise XbenchException(e)

    def clean(self):
        """Uninstall software on node

        Raises:
            XbenchException: [description]
        """
        self.logger.info("Uninstalling all components..")
        try:
            cluster = self.load_cluster()
            for env_c in self.envs:
                region_config = env_c.region_config
                MetricsServer().initialize(**region_config.get("metric_server", {}))
                clean_args = [
                    {"klass": member.get("klass"), "nodes": member.get("nodes")}
                    for member in cluster.group_nodes_by_name().values()
                    if member.get("env") == env_c.env.name
                ]

                noop = lambda x: x
                run_parallel(clean_args, noop, klass_instance_clean)

                cluster.bt = BackendTarget("", "", "", "", 0)
                self.save_cluster(cluster)
        except ValueError as e:
            raise XbenchException(
                f"{e}. Please check that klass in the form module.class"
            )
        except (
            NodeException,
            ShellSSHClientException,
            DriverException,
            BackendException,
        ) as e:
            raise XbenchException(e)
