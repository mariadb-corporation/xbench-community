#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
# Example: ./bin/xb.py --log-level INFO --log-dir /tmp/ -c test -t test_only -i performance


import argparse
import logging
import sys
import traceback
from logging.handlers import RotatingFileHandler

from cloud.exceptions import CloudException
from common.common import local_ip_addr, mkdir, validate_name_rfc1035
from xbench import (
    DeProvisioning,
    Provisioning,
    Reporting,
    SecurityCommands,
    WorkloadRunning,
    XbenchException,
    parse_unknown,
)
from xbench.cloud_commands import CloudCommands
from xbench.xcommands import xCommands

BENCH_LOG_HOME = "/tmp"
MAX_BYTES = 1024 * 1024
BACKUP_COUNT = 3
FILE_LOG_NAME = "xbench.log"

logger = logging.getLogger(__name__)


def defineArg(*args, **kwargs):
    return {"args": args, "kwargs": kwargs}


def add_defined_argument(parser: argparse.ArgumentParser, arg):
    parser.add_argument(*arg["args"], **arg["kwargs"])


def add_defined_arguments(parser: argparse.ArgumentParser, args: list):
    for a in args:
        add_defined_argument(parser, a)


def name_rfc1035_type(arg_value):
    if not validate_name_rfc1035(arg_value):
        raise argparse.ArgumentTypeError("Value does not comply with RFC1035.")
    return arg_value


ARG_CLUSTER = defineArg(
    "-c",
    "--cluster",
    action="store",
    dest="cluster",
    help="cluster name to provision",
    required=True,
    type=name_rfc1035_type,
)

ARG_LOG_LEVEL = defineArg(
    "-l",
    "--log-level",
    action="store",
    dest="log_level",
    default="INFO",
    help="Log Level: INFO|DEBUG|ERROR, default: INFO",
)

ARG_LOG_DIR = defineArg(
    "-o",
    "--log-dir",
    action="store",
    dest="log_dir",
    help=f"logging directory, default: {BENCH_LOG_HOME}",
    default=BENCH_LOG_HOME,
)

ARG_DRY_RUN = defineArg(
    "--dry-run",
    action="store_true",
    default=False,
    dest="dry_run",
    help="use dry run",
)

ARG_TOPO = defineArg(
    "-t",
    "--topo",
    action="store",
    dest="topo",
    help="topology from config file",
    required=True,
)

ARG_IMPL = defineArg(
    "-i",
    "--impl",
    action="store",
    dest="impl",
    help="implementation specification from impl.yaml",
    required=True,
)

ARG_PROVISION_STEP = defineArg(
    "-s",
    "--step",
    choices=["configure", "allocate", "make", "test", "install", "clean", "all"],
    default="all",
    help="""Provision step. Executes all steps (except clean) by default.
configure - Configures cluster.
allocate - Allocate instances in the Cloud
make - Prepare instance
test - Run self test.
install - Installs software on instances.
clean - Uninstall software on instances.""",
)

ARG_BENCHMARK = defineArg(
    "-b",
    "--benchmark",
    action="store",
    help="Benchmark to run (sysbench, javabench, etc.)",
    required=True,
)

ARG_WORKLOAD = defineArg(
    "-w",
    "--workload",
    action="store",
    help="Workload to run (9010, readonly, etc)",
    required=True,
)

ARG_ARTIFACT_DIR = defineArg(
    "-a",
    "--artifact-dir",
    action="store",
    dest="artifact_dir",
    help=f"Where to store workload artifacts, default is the same as --log-dir",
    default=None,
)

ARG_WORKLOAD_STEP = defineArg(
    "-s",
    "--step",
    choices=["test", "prepare", "run", "backup", "restore", "all"],
    default="all",
    help="""Workload step. Executes all steps (except backup/restore) by default.
test - Run self-test.
prepare - Create schemas and load data.
run - Run benchmark.
backup - Backup database
restore - Restore database""",
)

ARG_WORKLOAD_TAG = defineArg(
    "-g",
    "--tag",
    action="store",
    dest="tag",
    help=f"Workload tag; used for distinguish multiped workloads during the experiment",
    required=False,
)

ARG_TARGET = defineArg(
    "-p",
    "--target",
    action="store",
    help="Target for backup/restore, e.g. ftp, s3, (default: ftp)",
    default="ftp",
    required=False,
)

ARG_DEPROVISION_FORCE = defineArg(
    "-f",
    "--force",
    action="store_true",
    default=False,
    dest="force",
    help="""Force deprovisioning, a.k.a. the "nuke" command.
    In the nuke mode the cluster's resources will be requested by tag and deleted sequentially.
    """,
)

ARG_PROVISION_FORCE = defineArg(
    "-f",
    "--force",
    action="store_true",
    default=False,
    dest="force",
    help="""Force provisioning even cluster definition yaml file already exists
    """,
)

ARG_DEPROVISION_CLOUD = defineArg(
    "--cloud",
    action="store",
    default=None,
    dest="cloud",
    help="""Cloud for the force deprovisioning,
    """,
)

ARG_DEPROVISION_REGION = defineArg(
    "--region",
    action="store",
    default=None,
    dest="region",
    help="""Cloud region for the force deprovisioning,
    """,
)

ARG_REPORTING_NOTEBOOK = defineArg(
    "--notebook-name",
    action="store",
    default="results",
    dest="notebook_name",
    help="""Result notebook name (without extension),
    """,
)
ARG_REPORTING_NOTEBOOK_TITLE = defineArg(
    "--notebook-title",
    action="store",
    default="Performance results",
    dest="notebook_title",
    help="""Result notebook title,
    """,
)

ARG_REPORTING_YAML_CONFIG = defineArg(
    "--yaml-config",
    action="store",
    required=False,
    dest="yaml_config",
    help="""Yaml config file
    """,
)

ARG_CLUSTER_MEMBER = defineArg(
    "member",
    action="store",
    help="""Cluster member
    """,
)

ARG_SSH_COMMAND = defineArg(
    "ssh_command",
    action="store",
    nargs=argparse.REMAINDER,
    default="",
    help="""ssh command to run
    """,
)

ARG_SQL_COMMAND = defineArg(
    "sql_command",
    action="store",
    nargs=argparse.REMAINDER,
    default="",
    help="""sql command to run
    """,
)

ARG_SCP_COMMAND_LOCAL_FILE = defineArg(
    "local_file",
    action="store",
    default="",
    help="""local file
    """,
)

ARG_SCP_COMMAND_REMOTE_FILE = defineArg(
    "remote_file",
    action="store",
    default="",
    help="""remote file
    """,
)

ARG_SECURITY_ACTION = defineArg(
    "--action",
    action="store",
    default="list",
    dest="security_action",
    choices=["list", "addip", "delip"],
    help="list servers, storage, or both (default: %(default)s)",
)

ARG_SECURITY_IP = defineArg(
    "--ip",
    action="store",
    default=None,
    dest="ip_address",
    help="IP address to modify",
)


def provision(args, extra_impl_params):

    if not validate_name_rfc1035(args.cluster):
        raise XbenchException(
            f"Cluster name {args.cluster} must follow rfc1035:"
            " https://tools.ietf.org/html/rfc1035"
        )

    p = Provisioning(
        cluster_name=args.cluster,
        topo=args.topo,
        impl=args.impl,
        artifact_dir=args.artifact_dir or args.log_dir,
        dry_run=args.dry_run,
        extra_impl_params=extra_impl_params,
    )

    if p.cluster_yaml_exists() and args.step in ["all", "configure"] and not args.force:
        raise XbenchException(
            f"Cluster file {args.cluster}.yaml already exists. Use --force to override"
        )

    if args.step == "all":
        logger.info("Executing all provision steps")
        p.configure()
        p.allocate()
        p.self_test()
        p.make()
        p.install()
    elif args.step == "configure":
        p.configure()
    elif args.step == "allocate":
        p.allocate()
    elif args.step == "make":
        p.make()
    elif args.step == "test":
        p.self_test()
    elif args.step == "install":
        p.install()
    elif args.step == "clean":
        p.clean()


def workload(args, extra_impl_params):
    final_artifact_dir = None
    w = WorkloadRunning(
        cluster_name=args.cluster,
        benchmark_name=args.benchmark,
        workload_name=args.workload,
        artifact_dir=args.artifact_dir or args.log_dir,
        extra_impl_params=extra_impl_params,
        tag=args.tag,
    )
    if args.step == "all":
        logger.info("Executing all workload steps")
        w.self_test()
        w.prepare()
        final_artifact_dir = w.run()
    elif args.step == "test":
        w.self_test()
    elif args.step == "prepare":
        w.prepare()
    elif args.step == "run":
        w.run()
    elif args.step == "backup":
        w.backup(args.target)
    elif args.step == "restore":
        w.restore(args.target)
    return final_artifact_dir


def deprovision(args, extra_impl_params):
    d = DeProvisioning(
        cluster_name=args.cluster,
        dry_run=args.dry_run,
        force=args.force,
        cloud=args.cloud,
        cloud_region=args.region,
        artifact_dir=args.artifact_dir or args.log_dir,
    )
    if args.force == True and args.cloud is not None:
        logger.info(f"Deprovisioning cluster in nuke mode")
        d.nuke()
    else:
        logger.info(f"Deprovisioning cluster")
        d.clean()


def security(args, extra_impl_params):
    s = SecurityCommands(
        cloud=args.cloud,
        cloud_region=args.region,
    )

    ip_address = args.ip_address
    if ip_address is None:
        ip_address = local_ip_addr()

    if args.security_action == "list":
        s.list(ip_address)
    elif args.security_action == "addip":
        s.addip(ip_address)
    elif args.security_action == "delip":
        s.delip(ip_address)


def reporting(args, extra_impl_params):
    r = Reporting(
        cluster_name=args.cluster,
        benchmark_name=args.benchmark,
        artifact_dir=args.artifact_dir or args.log_dir,
        notebook_name=args.notebook_name,
        notebook_title=args.notebook_title,
        yaml_config=args.yaml_config,
    )
    r.run()


def ls_command(args, extra_impl_params):
    x = xCommands(cluster_name=args.cluster)
    x.ls()


def ssh_command(args, extra_impl_params):

    x = xCommands(cluster_name=args.cluster)
    x.ssh(args.member, args.ssh_command)


def sql_command(args, extra_impl_params):

    x = xCommands(cluster_name=args.cluster)
    x.sql(args.member, args.sql_command)


def send_command(args, extra_impl_params):

    x = xCommands(cluster_name=args.cluster)
    x.send(args.member, args.local_file, args.remote_file)


def recv_command(args, extra_impl_params):

    x = xCommands(cluster_name=args.cluster)
    x.recv(args.member, args.remote_file, args.local_file)


def stop_command(args, extra_impl_params):
    cc = CloudCommands(cluster_name=args.cluster)
    cc.start_stop_cluster("stop")


def start_command(args, extra_impl_params):
    cc = CloudCommands(cluster_name=args.cluster)
    cc.start_stop_cluster("start")


def main():
    epilog_string = """Examples:

    Run end-to-end workflow in Xbench, e.g. provision -> workload -> deprovision
    python bin/xb.py run -c itest_cluster -t test_only -i test_only -b sysbench -w itest

    Run all steps (except clean) for provision command
    python bin/xb.py provision -c itest_cluster -t test_only -i test_only

    Run all steps for workload command
    python bin/xb.py workload -c itest_cluster -t test_only -i test_only -b sysbench -w itest

    Deprovision a cluster
    python bin/xb.py deprovision -c test -t test_only -i test_only
    """
    common_parser = argparse.ArgumentParser(add_help=False)
    add_defined_arguments(
        common_parser, [ARG_CLUSTER, ARG_LOG_LEVEL, ARG_LOG_DIR, ARG_DRY_RUN]
    )

    parser = argparse.ArgumentParser(
        description="Xbench - Performance Testing Framework",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=epilog_string,
    )

    subparsers = parser.add_subparsers(title="Commands", dest="command", required=True)

    provision_parser = subparsers.add_parser(
        "provision",
        aliases=["p"],
        help="Provision cluster [configure, make, test, install, clean, all]",
        parents=[common_parser],
        formatter_class=argparse.RawTextHelpFormatter,
    )
    add_defined_arguments(
        provision_parser,
        [ARG_TOPO, ARG_IMPL, ARG_PROVISION_STEP, ARG_PROVISION_FORCE, ARG_ARTIFACT_DIR],
    )
    provision_parser.set_defaults(func=provision)

    workload_parser = subparsers.add_parser(
        "workload",
        aliases=["w"],
        help="Run benchmark against cluster [test, prepare, run, all]",
        parents=[common_parser],
        formatter_class=argparse.RawTextHelpFormatter,
    )
    add_defined_arguments(
        workload_parser,
        [
            ARG_BENCHMARK,
            ARG_WORKLOAD,
            ARG_ARTIFACT_DIR,
            ARG_WORKLOAD_STEP,
            ARG_WORKLOAD_TAG,
            ARG_TARGET,
        ],
    )
    workload_parser.set_defaults(func=workload)

    deprovision_parser = subparsers.add_parser(
        "deprovision",
        aliases=["d"],
        help="Deprovision all instances in cluster",
        parents=[common_parser],
    )
    add_defined_arguments(
        deprovision_parser,
        [
            ARG_DEPROVISION_FORCE,
            ARG_DEPROVISION_CLOUD,
            ARG_DEPROVISION_REGION,
            ARG_ARTIFACT_DIR,
        ],
    )
    deprovision_parser.set_defaults(func=deprovision)

    security_parser = subparsers.add_parser(
        "security",
        aliases=["s"],
        help="Secure a cloud access",
        parents=[common_parser],
    )
    add_defined_arguments(
        security_parser,
        [
            ARG_SECURITY_ACTION,
            ARG_SECURITY_IP,
            ARG_DEPROVISION_CLOUD,
            ARG_DEPROVISION_REGION,
        ],
    )
    security_parser.set_defaults(func=security)

    # Reporting
    reporting_parser = subparsers.add_parser(
        "report",
        aliases=["t"],
        help="produce a report after workload finished",
        parents=[common_parser],
    )
    add_defined_arguments(
        reporting_parser,
        [
            ARG_BENCHMARK,
            ARG_ARTIFACT_DIR,
            ARG_REPORTING_NOTEBOOK,
            ARG_REPORTING_NOTEBOOK_TITLE,
            ARG_REPORTING_YAML_CONFIG,
        ],
    )
    reporting_parser.set_defaults(func=reporting)

    run_parser = subparsers.add_parser(
        "run",
        aliases=["r"],
        help="Run end-to-end workflow, e.g. provision -> workload -> deprovision",
        parents=[common_parser],
    )
    add_defined_arguments(
        run_parser,
        [
            ARG_TOPO,
            ARG_IMPL,
            ARG_BENCHMARK,
            ARG_WORKLOAD,
            ARG_ARTIFACT_DIR,
            ARG_DEPROVISION_FORCE,
            ARG_WORKLOAD_TAG,
            ARG_DEPROVISION_CLOUD,
            ARG_DEPROVISION_REGION,
            ARG_REPORTING_NOTEBOOK,
            ARG_REPORTING_NOTEBOOK_TITLE,
            ARG_REPORTING_YAML_CONFIG,
        ],
    )

    # ls command
    ls_command_parser = subparsers.add_parser(
        "ls",
        help="Show (List) Cluster info",
        parents=[common_parser],
    )
    add_defined_arguments(
        ls_command_parser,
        [],
    )
    ls_command_parser.set_defaults(func=ls_command)

    # SSH command
    ssh_command_parser = subparsers.add_parser(
        "ssh",
        help="ssh command to the cluster member",
        parents=[common_parser],
    )
    add_defined_arguments(
        ssh_command_parser,
        [
            ARG_CLUSTER_MEMBER,
            ARG_SSH_COMMAND,
        ],
    )
    ssh_command_parser.set_defaults(func=ssh_command)

    # SQL command
    sql_command_parser = subparsers.add_parser(
        "sql",
        help="sql command to the cluster member (proxy or backend)",
        parents=[common_parser],
    )
    add_defined_arguments(
        sql_command_parser,
        [
            ARG_CLUSTER_MEMBER,
            ARG_SQL_COMMAND,
        ],
    )
    sql_command_parser.set_defaults(func=sql_command)

    # Send SCP command
    send_command_parser = subparsers.add_parser(
        "send",
        help="send file to the cluster member",
        parents=[common_parser],
    )
    add_defined_arguments(
        send_command_parser,
        [ARG_CLUSTER_MEMBER, ARG_SCP_COMMAND_LOCAL_FILE, ARG_SCP_COMMAND_REMOTE_FILE],
    )
    send_command_parser.set_defaults(func=send_command)

    # recv command parser
    # Send SCP command
    recv_command_parser = subparsers.add_parser(
        "recv",
        help="recv file from cluster member",
        parents=[common_parser],
    )
    add_defined_arguments(
        recv_command_parser,
        [ARG_CLUSTER_MEMBER, ARG_SCP_COMMAND_REMOTE_FILE, ARG_SCP_COMMAND_LOCAL_FILE],
    )
    recv_command_parser.set_defaults(func=recv_command)

    # stop cluster parser
    stop_command_parser = subparsers.add_parser(
        "stop",
        help="shutdown all members of a cluster (instances and storage will not be terminated)",
        parents=[common_parser],
    )
    add_defined_arguments(
        stop_command_parser, []
    )
    stop_command_parser.set_defaults(func=stop_command)

    # start cluster parser
    start_command_parser = subparsers.add_parser(
        "start",
        help="start all members of a shutdown cluster",
        parents=[common_parser],
    )
    add_defined_arguments(
        start_command_parser, []
    )
    start_command_parser.set_defaults(func=start_command)

    # This allow pass any additional parameters. So far it allow pass only impl params
    args, unknown = parser.parse_known_args()
    extra_impl_params = parse_unknown(unknown)

    log_file_dir = f"{args.log_dir}/{args.cluster}"
    mkdir(log_file_dir)
    file_handler = RotatingFileHandler(
        filename=f"{log_file_dir}/{FILE_LOG_NAME}",
        maxBytes=MAX_BYTES,
        backupCount=BACKUP_COUNT,
    )

    stdout_handler = logging.StreamHandler(sys.stdout)
    handlers = [file_handler, stdout_handler]

    if args.log_level == "DEBUG":
        log_format = "%(asctime)s - %(levelname)s - %(name)s - %(message)s"
    else:
        log_format = "%(asctime)s - %(levelname)s - %(message)s"
    logging.basicConfig(
        format=log_format,
        datefmt="%Y-%m-%d %H:%M:%S",
        level=args.log_level,
        handlers=handlers,
    )
    logger.info(f"Log directory is set as {log_file_dir}")

    try:
        if args.command in ("deprovision", "d"):
            # validate dependent args
            if args.force and not (args.cloud and args.region):
                logger.error("Nuke mode (-f) requires --cloud and --region arguments!")
                deprovision_parser.print_usage()
                exit(1)
        if args.command in ("run", "r"):
            if args.benchmark is None:
                logger.error("Missing -b/--benchmark argument!")
                parser.print_usage()
                exit(1)
            elif args.workload is None:
                logger.error("Missing -w/--workload argument!")
                parser.print_usage()
                exit(1)
            logger.info("Running end-to-end workflow")
            args.step = "all"
            provision(args, extra_impl_params)
            artifact_dir = workload(
                args, extra_impl_params
            )  # Workload if run in all steps returns its artifact directory (which contains timestamp)
            deprovision(args, extra_impl_params)
            args.artifact_dir = artifact_dir
            reporting(args, extra_impl_params)
        else:
            args.func(args, extra_impl_params)
        logger.info("Xbench workflow complete!")

    except (XbenchException, CloudException) as exc:
        logger.error(f"Unrecoverable error has occurred: {exc}")
        if args.log_level == "DEBUG":
            log_trace(exc)
        exit(1)

    except KeyboardInterrupt:
        logger.warning("Got keyboard interrupt, exiting ...")
        exit(1)

    except Exception as exc:
        logger.error(f"Unexpected error has occurred: {exc}")
        log_trace(exc)
        exit(1)

    return 0


def log_trace(exc):
    tb_str = traceback.format_exception(
        etype=type(exc), value=exc, tb=exc.__traceback__
    )
    logger.error("".join(tb_str))


if __name__ == "__main__":
    main()
