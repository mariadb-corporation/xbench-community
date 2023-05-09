import logging
import os
import re
import shutil
import time
from io import StringIO
from typing import List

import jinja2
import pandas as pd

from benchmark.abstract_benchmark import AbstractBenchmarkRunner
from benchmark.exceptions import BenchmarkException
from common.common import get_class_from_klass
from common.retry_decorator import backoff_with_jitter, retry
from compute import Node, NodeException, PsshClient, SshClientTimeoutException
from lib import XbenchConfig

from .exceptions import (
    SysbenchException,
    SysbenchFatalException,
    SysbenchOutputParseException,
)

# TODO replace p95_latency vs 95th_latency to be compatible with Clustrixbench

DEFAULT_COMMAND_TIMEOUT = 300
DEFAULT_SLEEP_TIME = 30  # sleep time between threads
RESULT_PRECISION = 2  # How many digits after decimal point to keep
SYSBENCH_RESULT_FIELDS = [
    "concurrency",
    "throughput",
    "avg_latency",
    "stddev",
    "p95_latency",
    "errors",
]

ERROR_PCT = 5  # Maximum % difference between expected rows and actual rows

tpcc_scale_factors = {
    "customer": "SCALE*30000",
    "district": "SCALE*10",
    "item": "100000",  # fixed value
    "warehouse": "SCALE",
}


class SysbenchRunner(AbstractBenchmarkRunner):
    """Run sysbench on multiple drivers"""

    def __init__(self, nodes: List[Node], **kwargs):
        self.nodes = nodes
        self.logger = logging.getLogger(__name__)
        self.kwargs = kwargs
        # Open sysbench.yaml to get run and prepare commands
        self.lua = kwargs.get("lua_name", None)
        self.artifact_dir = kwargs.get(
            "artifact_dir", None
        )  # Artifact dir has been adjusted to include cluster_name and datetime
        self.workload_name = kwargs.get("workload_name", None)

        self.workload_config = XbenchConfig().get_key_from_yaml(
            yaml_file_name="sysbench.yaml", key_name=self.lua, use_defaults=True
        )

        pssh_config = {
            "hostnames": self._all_public_ips(),
            "username": self.head_node.vm.ssh_user,
            "key_file": self.head_node.vm.key_file,
        }
        self.pssh = PsshClient(**pssh_config)
        self.backend = kwargs.get("backend")

    @property
    def head_node(self):
        return self.nodes[0]

    def _all_public_ips(self) -> List:
        ips = []
        for n in self.nodes:
            ips.append(n.vm.network.get_public_iface())
        return ips

    # TODO print database size after prepare. That would required knowledge of database we are dealing with
    def prepare(self):
        """Run prepare command"""
        prepare_command = self.evaluate_command("prepare")
        self.logger.info(f"Running prepare command {prepare_command}")
        # Next command has small timeout for tpc-c
        # TODO adjust timeout based on scrip name and number of rows??
        self.head_node._unsafe_run(prepare_command)
        if self.kwargs.get("post_data_load"):
            self.backend.post_data_load(
                database=self.kwargs.get("database")
            )  # This uses the fact that workload.py pass it to runner class

    def data_check(self):
        """Check that data has been generated correctly"""
        self.logger.info("Running Data integrity check")
        if self.lua.startswith("oltp"):
            self.backend.db_connect()
            tables = self.kwargs.get("tables")
            desired_rows = self.kwargs.get("table_size")
            for k in range(1, tables + 1):
                q = f"select count(*) as row_num from sbtest{k}"
                row = self.backend.select_one_row(q)
                actual_rows = row.get("row_num")
                if actual_rows != desired_rows:
                    raise BenchmarkException(
                        f"Integrity check failed for table sbtest{k}: Actual rows:"
                        f" {actual_rows}, Desired rows: {desired_rows} "
                    )
        if self.lua.startswith("tpcc"):
            self.backend.db_connect()
            SCALE = self.kwargs.get(
                "scale"
            )  # this is a very special variable required for data check
            tables = self.kwargs.get("tables")
            for i in range(1, tables + 1):
                for k, v in tpcc_scale_factors.items():
                    q = f"select count(*) as row_num from {k}{i}"
                    row = self.backend.select_one_row(q)
                    actual_rows = int(row.get("row_num"))
                    desired_rows = eval(v)  # this is already int
                    err_pct = abs(1 - actual_rows / desired_rows) * 100
                    if err_pct > ERROR_PCT:
                        raise BenchmarkException(
                            f"Integrity check failed for table {k}{i}: Actual rows:"
                            f" {actual_rows}, Desired rows: {desired_rows} "
                        )

        else:
            self.logger.warn(
                f"Data integrity check has not been implemented for {self.lua}"
            )

    # TODO: driver actually drop database that maybe even faster then clean up command below
    def cleanup(self):
        """Run clean up command"""
        cleanup_command = self.evaluate_command("cleanup")
        self.logger.info(f"Running cleanup command {cleanup_command}")
        self.head_node.run(cleanup_command)

    def evaluate_command(self, cmd: str, **extra_kwargs):
        try:
            connection_template = self.workload_config.get("connection")

            # SSL mode 'mysql-ssl=on' or pgsql-sslmode=verifa-ca
            enable_ssl = self.kwargs.get("ssl", False)
            if enable_ssl:
                dialect = self.kwargs.get("dialect")
                if dialect == "mysql":

                    ssl_ca_file = enable_ssl.get("ssl_ca")
                    if (
                        ssl_ca_file
                    ):  # cert file copied to certs directory before workload starts
                        ssl_ca_file = os.path.basename(ssl_ca_file)
                        ssl_ca = f"--mysql-ssl-ca=$XBENCH_HOME/certs/{ssl_ca_file}"
                    else:
                        ssl_ca = ""

                    ssl_mode = (  # How to specify ca files https://aws.amazon.com/blogs/database/running-sysbench-on-rds-mysql-rds-mariadb-and-amazon-aurora-mysql-via-ssl-tls/
                        f"--mysql-ssl=on {ssl_ca}"
                    )
                else:
                    ssl_mode = "--pgsql-sslmode=verifa-ca"
            else:
                ssl_mode = ""

            connection_cmd = jinja2.Template(connection_template).render(
                **self.kwargs | {"ssl_mode": ssl_mode}
            )
            command_template = self.workload_config.get(cmd)
            all_kwargs = self.kwargs | extra_kwargs | {"connection": connection_cmd}
            command_command = jinja2.Template(command_template).render(**all_kwargs)

            return command_command
        except jinja2.exceptions.UndefinedError as e:
            raise SysbenchException(
                f"There is a problem with sysbench template in sysbench.yaml: {e}"
            )

    # TODO Stop if latency above some limit from workload.yaml
    def run(self):
        success = True
        threads = self.kwargs.get("threads")
        repeats = self.kwargs.get("repeats")

        all_results = pd.DataFrame()  # Contains all repeats
        num_drivers = len(self.nodes)
        # For the sole logging purpose only
        run_command = self.evaluate_command("run", **{"t": "$t"})
        self.logger.info(f"Run command {run_command}")

        self.logger.info(f"Using {num_drivers} drivers to generate load")
        try:
            for r in range(1, repeats + 1):

                if self.kwargs.get("pre_workload_run"):
                    self.backend.pre_workload_run()
                this_repeat_results = []
                for t in threads:
                    time.sleep(DEFAULT_SLEEP_TIME)
                    if self.kwargs.get("pre_thread_run"):
                        self.backend.pre_thread_run()

                    self.logger.info(f"Running repeat {r}, thread: {t}")

                    # Not super genius decision. Don't allocate 3 drivers for 8 threads!
                    per_driver_t = int(t / num_drivers)

                    # this will also save raw data
                    thread_results = self.run_thread(per_driver_t, r)
                    self.logger.debug(thread_results)
                    this_repeat_results.extend(thread_results)

                # At the end of full repeat print data frame
                df = self.save_print_one_repeat(
                    repeat=r,
                    num_drivers=num_drivers,
                    results=this_repeat_results,
                )
                # Now we need collect overall run results, but before we need add repeat
                all_results = pd.concat([all_results, df])
        except BenchmarkException as e:
            self.logger.error(f"Benchmark failed with: {e}")
            success = False
        else:
            self.logger.info("Benchmark completed successfully")
        finally:
            if success:
                # Print and save summary
                self.save_print_summary(df=all_results)
                self.logger.info(f"Raw output has saved to the {self.artifact_dir}")
            else:
                raise BenchmarkException("Benchmark failed")

    def save_print_summary(self, df: pd.DataFrame):
        """Print overall summary for all repeats

        Args:
            df (pd.DataFrame): raw results
        """
        df_summary = df.groupby(["concurrency"]).agg(
            {
                "throughput": ["mean"],
                "avg_latency": ["mean"],
                "stddev": ["max"],
                "p95_latency": ["max"],
                "errors": ["sum"],
            }
        )
        df_summary.reset_index(inplace=True)
        df_summary.columns = SYSBENCH_RESULT_FIELDS
        df_summary = df_summary.round(RESULT_PRECISION)
        self.logger.info(
            f"======= Overall results ==========\n{df_summary.to_string(index=False)}"
        )
        # And save it
        file_name = os.path.join(self.artifact_dir, f"{self.workload_name}_summary.csv")
        self.logger.info(f"Summary results saved as {file_name}")
        df_summary.to_csv(file_name, index=False)

    def save_print_one_repeat(
        self, repeat: int, num_drivers: int, results: List[tuple]
    ) -> pd.DataFrame:
        """Summarize and display sysbench results

        Args:
            results (list[tuple]): _description_
        """
        columns = [
            "concurrency",
            "throughput",
            "queries",
            "stddev",
            "transactions",
            "total_response_time",
            "p95_latency",
            "errors",
        ]
        df = pd.DataFrame.from_records(results, columns=columns)
        df = df.astype(float)
        grouped_multiple = df.groupby("concurrency").agg(
            {
                "throughput": ["sum"],
                "queries": ["sum"],
                "stddev": ["max"],
                "transactions": ["sum"],
                "total_response_time": ["sum"],
                "p95_latency": ["max"],
                "errors": ["sum"],
            }
        )
        grouped_multiple.reset_index(inplace=True)

        grouped_multiple.columns = columns

        grouped_multiple["avg_latency"] = (
            grouped_multiple["total_response_time"] / grouped_multiple["transactions"]
        )
        grouped_multiple["concurrency"] = num_drivers * grouped_multiple[
            "concurrency"
        ].astype(int)

        grouped_multiple["avg_latency"] = grouped_multiple["avg_latency"].astype(float)

        # Final DF
        df_final = grouped_multiple[SYSBENCH_RESULT_FIELDS].round(RESULT_PRECISION)

        self.logger.info(
            f"======= Sysbench results ==========\n{df_final.to_string(index=False)}"
        )

        # And save it
        file_name = os.path.join(
            self.artifact_dir, f"{self.workload_name}_{repeat}.csv"
        )
        self.logger.info(f"Results for repeat {repeat} saved as {file_name}")
        df_final.to_csv(file_name, index=False)
        df_final["repeat"] = repeat
        return df_final

    @retry(
        (
            NodeException,
            SysbenchOutputParseException,
            SshClientTimeoutException,
            SysbenchFatalException,
        ),
        BenchmarkException,
        max_delay=600,
        delays=backoff_with_jitter(delay=3, attempts=3, cap=30),
    )
    def run_thread(self, t: int, r: int) -> List[tuple]:
        """Run single thread of sysbench

        Args:
            t (int): thread number
            r (int): repeat attempt

        Returns:
            tuple: sysbench parsed results
        """
        # I need to clean driver(s) in case of re-try
        cmd = "pkill -9 sysbench || true"
        self.pssh.run(cmd, timeout=30)  # 30 sec should be enough

        timeout = (
            self.kwargs.get("time", 0) + self.kwargs.get("warmup_time", 0) + 30
        )  # Add buffer to timeout
        run_command = self.evaluate_command("run", **{"t": t})
        self.logger.debug(f"Running run command {run_command} with timeout {timeout}")

        # TODO add workload 9010|8020 as parameter for parser down below
        cmd = (  # This should send metrics to prometheus
            f"{run_command} | /xbench/workload-exporter/bin/sysbench_parser.sh"
        )

        thread_results: List = []  # contains results for each driver

        all_hosts_sysbench_output = self.pssh.run(cmd, timeout=timeout)
        for host_output in all_hosts_sysbench_output:
            hostname = host_output.get("hostname")
            sysbench_output = host_output.get("stdout", "")
            # Let's save it first
            file_name = os.path.join(
                self.artifact_dir, f"{hostname}_{self.workload_name}_{r}_{t}.out"
            )
            self.save_sysbench_output(file_name, sysbench_output)
            single_host_results = self.parse_output(sysbench_output)
            thread_results.append(single_host_results)
        return thread_results

    def save_sysbench_output(self, file_name: str, sysbench_output: str):
        """Save output to the benchmark directory

        Args:
            file_name (str): full path
            sysbench_output (str): sysbench output
        """
        sysbench_output_io = StringIO(sysbench_output)
        with open(file_name, "w") as fd:
            sysbench_output_io.seek(0)
            shutil.copyfileobj(sysbench_output_io, fd)

    # TODO ignored errors: If > 0 issue a warning I think
    def parse_output(self, sysbench_output: str) -> tuple:
        """Parse plain sysbench output

        Args:
            sysbench_output (str): sysbench plain output

        Returns:
            tuple: thds, tps, qps, p95_latency, avg, stddev
        """

        thds = (
            tps
        ) = (
            qps
        ) = (
            avg
        ) = stddev = transactions = total_response_time = p95_latency = errors = 0.0

        seen_latency = False
        seen_sql_statistics = False

        try:
            sysbench_output_io = StringIO(sysbench_output)

            for line in sysbench_output_io.readlines():
                if line.startswith("FATAL:") or line.startswith("Segmentation fault"):
                    raise SysbenchFatalException(line)

                if line.startswith("SQL statistics:"):
                    seen_sql_statistics = True
                elif line.startswith("Latency (ms):"):
                    seen_latency = True

                if line.startswith("Histogram latency"):
                    m = re.search(
                        r"^Histogram latency \(avg\/stddev\): (\d+\.\d+) \/ (\d+\.\d+)",
                        line,
                    )
                    avg = float(m.group(1)) if m is not None else 0
                    stddev = float(m.group(2)) if m is not None else 0

                if not seen_sql_statistics:
                    if line.startswith("Number of threads"):
                        m = re.search("^Number of threads: (\d+)", line)
                        thds = float(m.group(1)) if m is not None else 0

                if seen_sql_statistics and not seen_latency:
                    if line.startswith("transactions:"):
                        m = re.search("^transactions:\s+ (\d+)\s+\((\d+\.\d+)", line)
                        transactions = float(m.group(1)) if m is not None else 0
                        tps = float(m.group(2)) if m is not None else 0
                    elif line.startswith("queries:"):
                        m = re.search("^queries:\s+ \d+\s+\((\d+\.\d+)", line)
                        qps = float(m.group(1)) if m is not None else 0
                    elif line.startswith("ignored errors:"):
                        m = re.search("^ignored errors:\s+ (\d+)", line)
                        errors = float(m.group(1)) if m is not None else 0

                if seen_latency:
                    if line.startswith("95th"):
                        m = re.search("^95th percentile:\s+(\d+\.\d+)", line)
                        p95_latency = float(m.group(1)) if m is not None else 0

                    elif line.startswith("sum:"):
                        m = re.search("sum:\s+ (\d+\.\d+)", line)
                        total_response_time = float(m.group(1)) if m is not None else 0

            if not tps > 0:
                raise SysbenchOutputParseException(
                    "TPS is zero in Sysbench output. Did sysbench crash?"
                )

            return (
                thds,
                tps,
                qps,
                stddev,
                transactions,
                total_response_time,
                p95_latency,
                errors,
            )
        except AttributeError as e:
            raise SysbenchOutputParseException(
                "Enable to parse output.Sysbench failed? "
            )

    def get_scale_string(self):
        scale_string = ""
        if self.kwargs.get("bench") == "oltp":
            scale_string = (
                f"{self.kwargs.get('tables')}x{self.kwargs.get('table_size')}"
            )
        else:  # tpcc uses scale
            scale_string = f"{self.kwargs.get('tables')}x{self.kwargs.get('scale')}"

        return scale_string
