import json
import os
import re
import time
from datetime import datetime
from enum import Enum
from glob import glob
from typing import Dict, List, Optional

import pandas as pd

from benchmark.abstract_benchmark import AbstractBenchmarkRunner
from benchmark.exceptions import BenchmarkException
from common.common import get_class_from_klass
from compute import MultiNode, Node
from lib.file_template import FileTemplate, FileTemplateException

DEFAULT_COMMAND_TIMEOUT = 300
DEFAULT_SLEEP_TIME = 60  # sleep time between threads

ERROR_PCT = 5  # Maximum % difference between expected rows and actual rows

EXTRA_BENCHBASE_TIMEOUT = (
    600  # sometime java needs an extra time for clean up after the test
)

tpcc_scale_factors = {
    "customer": "SCALE*30000",
    "district": "SCALE*10",
    "item": "100000",  # fixed value
    "oorder": "SCALE*30000",
    "warehouse": "SCALE",
}
# Check https://docs.snowflake.com/en/user-guide/sample-data-tpch.html#:~:text=%E2%80%9CTPC%2DH%20is%20a%20decision,have%20broad%20industry%2Dwide%20relevance.
# https://www.tpc.org/tpc_documents_current_versions/pdf/tpc-h_v3.0.1.pdf
tpch_scale_factors = {
    "supplier": "SCALE*10000",
    "part": "SCALE*200000",
    "customer": "SCALE*150000",
    "nation": "25",
    "region": "5",
}
BENCHBASE_RESULT_FIELDS = ["concurrency", "throughput", "avg_latency", "p90_latency"]
RESULT_PRECISION = 2


class BenchmarkStep(str, Enum):
    run = "run"
    prepare = "prepare"


class BenchbaseRunner(MultiNode, AbstractBenchmarkRunner):
    """Run benchbase on driver(s)"""

    def __init__(self, nodes: List[Node], **kwargs):
        """Implements CMU benchbase

        Args:
            nodes (List[Node]): list of drivers
            kwargs: bt + workload conf. Check WorkloadRunning run method
        """

        MultiNode.__init__(self, nodes)

        self.kwargs = kwargs
        self.artifact_dir = kwargs.get(
            "artifact_dir", None
        )  # Artifact dir has been adjusted to include cluster_name and datetime
        self.workload_name = kwargs.get("workload_name", None)
        self.bench = kwargs.get("bench")

        self.backend = kwargs.get("backend")
        self.product = self.kwargs.get("product", "").replace(
            "-", "_"
        )  #  In java "-" is not allowed
        self.num_drivers = len(self.nodes)

    @staticmethod
    def escape(str_xml: str):
        str_xml = str_xml.replace("&", "&amp;")
        str_xml = str_xml.replace("<", "&lt;")
        str_xml = str_xml.replace(">", "&gt;")
        str_xml = str_xml.replace('"', "&quot;")
        str_xml = str_xml.replace("'", "&apos;")
        return str_xml

    def get_config_data(self, step: Optional[BenchmarkStep] = BenchmarkStep.run) -> str:
        if isinstance(self.kwargs.get("terminals"), list):
            self.kwargs["terminals"] = self.kwargs.get("terminals")[0]
        if isinstance(self.kwargs.get("terminals_tpcc"), list):
            self.kwargs["terminals_tpcc"] = self.kwargs.get("terminals_tpcc")[0]
        if isinstance(self.kwargs.get("terminals_chbenchmark"), list):
            self.kwargs["terminals_chbenchmark"] = self.kwargs.get(
                "terminals_chbenchmark"
            )[0]

        try:
            ft = FileTemplate(filename=f"benchbase_xml/{self.bench}_config.xml")
            hosts = (",").join(
                [
                    host + ":" + str(self.kwargs.get("port"))
                    for host in self.kwargs.get("host").split(",")
                ]
            )
            render = ft.render(
                **self.kwargs
                | {"hosts": hosts}
                | {"password": self.escape(self.kwargs.get("password", ""))}
                | {"step": step.value}
            )
        except FileTemplateException as e:
            raise BenchmarkException(e)

        return render

    def save_config_data(
        self, config_file_name, step: Optional[BenchmarkStep] = BenchmarkStep.run
    ):
        config_data = self.get_config_data(step=step)

        with open(f"/tmp/{config_file_name}", "w") as xml:
            xml.write(config_data)

        # Need to use scp to preserve quotes
        self.scp_to_all_nodes(
            f"/tmp/{config_file_name}",
            f"$XBENCH_HOME/benchbase/{config_file_name}",
        )
        # TODO: Clean up /tmp

    def setup(self):
        driver_memory = round(self.head_node.memory_mb * 0.8)
        cmd = f"""
        cd $XBENCH_HOME/benchbase
        export MAVEN_OPTS='-Xmx{driver_memory}m'
        ./mvnw clean package -P {self.product} -Dmaven.test.skip
        mv target/benchbase-{self.product}.tgz ../
        cd ..
        tar xvf benchbase-{self.product}.tgz
        """
        output = self.head_node.run(cmd)
        self.logger.debug(output)
        self.logger.info("Setup complete")

    # Prepare can use only one node until ths issue get fixed
    # https://github.com/cmu-db/benchbase/issues/209
    def prepare(self):
        config_file_name = f"{self.product}_{self.bench}_config.xml"
        self.save_config_data(
            config_file_name=config_file_name, step=BenchmarkStep.prepare
        )
        self.setup()
        driver_memory = round(self.head_node.memory_mb * 0.8)
        java_opts = f"-Xmx{driver_memory}m"
        # Composite benchmarks require multiple schemas to be created/loaded
        bench = f"tpcc,{self.bench}" if self.bench == "chbenchmark" else self.bench
        prepare_cmd = f"""
        cd $XBENCH_HOME/benchbase-{self.product}
        java {java_opts} -jar benchbase.jar -b {bench} -c $XBENCH_HOME/benchbase/{config_file_name} --create=true --load=true --execute=false
        """
        self.logger.info(f"Loading {self.kwargs.get('scale')} warehouses")
        output = self.head_node._unsafe_run(prepare_cmd)
        if self.kwargs.get("post_data_load"):
            self.backend.post_data_load(
                database=self.kwargs.get("database")
            )  # This uses the fact that workload.py pass it to runner class
        self.logger.debug(output)
        self.logger.info("Load complete")

    # TODO add chbench and tpc-h
    def data_check(self):
        """Check that data has been generated correctly"""
        self.logger.info("Running Data integrity check")
        if self.bench == "tpcc":
            self.backend.db_connect()
            SCALE = self.kwargs.get(
                "scale"
            )  # this is a very special variable required for data check
            for k, v in tpcc_scale_factors.items():
                q = f"select count(*) as row_num from {k}"
                row = self.backend.select_one_row(q)
                actual_rows = int(row.get("row_num"))
                desired_rows = eval(v)  # this is already int
                err_pct = abs(1 - actual_rows / desired_rows) * 100
                if err_pct > ERROR_PCT:
                    raise BenchmarkException(
                        f"Integrity check failed for table {k}: Actual rows:"
                        f" {actual_rows}, Desired rows: {desired_rows} "
                    )
        else:
            self.logger.warn(
                f"Data integrity check has not been implemented for {self.bench}"
            )

    def run(self):
        """Prepare has to be run before run once, otherwise run will fail."""

        self.cleanup()
        success = True
        if self.bench == "chbenchmark":
            terminals = (
                [self.kwargs.get("terminals_tpcc")]
                if isinstance(self.kwargs.get("terminals_tpcc"), int)
                else self.kwargs.get("terminals_tpcc")
            )

            terminals_chbenchmark = (
                [self.kwargs.get("terminals_chbenchmark")]
                if isinstance(self.kwargs.get("terminals_chbenchmark"), int)
                else self.kwargs.get("terminals_chbenchmark")
            )

        else:
            terminals = (
                [self.kwargs.get("terminals")]
                if isinstance(self.kwargs.get("terminals"), int)
                else self.kwargs.get("terminals")
            )
        config_file_name = f"{self.product}_{self.bench}_config.xml"
        self.save_config_data(config_file_name=config_file_name, step=BenchmarkStep.run)
        repeats = self.kwargs.get("repeats")
        now = datetime.now().strftime("%Y%m%d_%H%M%S")
        run_outdir = f"{now}_benchbase_{self.bench}"
        self.logger.info(f"Using {self.num_drivers} drivers to generate load")
        driver_memory = round(self.head_node.memory_mb * 0.8)
        java_opts = f"-Xmx{driver_memory}m"
        # Composite benchmarks require multiple schemas to be accessed
        bench = f"tpcc,{self.bench}" if self.bench == "chbenchmark" else self.bench

        # Summary of all repetitions
        summary_query_data: Dict[int, Dict] = {}
        extra_params = ""
        if self.kwargs.get("raw_output"):
            extra_params = "-r"
        if self.kwargs.get("sampling_window"):
            sampling_window = self.kwargs.get("sampling_window")
            extra_params = f"{extra_params} -s {sampling_window}"
        try:
            repeat_runs = 0
            terminal_runs = []
            all_results = pd.DataFrame()
            for r in range(1, repeats + 1):
                repeat_runs = r
                if self.kwargs.get("pre_workload_run"):
                    self.backend.pre_workload_run()
                # All the queries all the terminals for the given repeat
                this_repeat_queries_results: Dict[int, pd.DataFrame] = {}
                this_repeat_results = []
                for i in range(len(terminals)):
                    t = terminals[i]  # it can be zero for chbenchmark
                    terminal_runs.append(t)
                    query_terminals = (
                        terminals_chbenchmark[i] if self.bench == "chbenchmark" else t
                    )
                    terminal_path = (
                        f"{t}_{query_terminals}"
                        if self.bench == "chbenchmark"
                        else f"{t}"
                    )

                    time.sleep(DEFAULT_SLEEP_TIME)
                    if self.kwargs.get("pre_thread_run"):
                        self.backend.pre_thread_run()
                    per_driver_t = int(t / self.num_drivers)
                    outdir = f"{terminal_path}_terminals_run_{r}"
                    remote_outdir = f"{run_outdir}/{outdir}"

                    terminals_clause = (
                        f"--terminals_tpcc {t} --terminals_chbenchmark"
                        f" {terminals_chbenchmark[i]}"
                        if self.bench == "chbenchmark"
                        else f"--terminals {per_driver_t}"
                    )
                    cmd = f"""
                    cd $XBENCH_HOME
                    python3 benchbase/scripts/update_config.py --config $XBENCH_HOME/benchbase/{config_file_name} {terminals_clause} --randomseed %s
                    cd benchbase-{self.product}
                    java {java_opts} -jar benchbase.jar -b {bench} -c $XBENCH_HOME/benchbase/{config_file_name} --create=false --load=false --execute=true -d /tmp/{remote_outdir}_%s -jh /tmp/{remote_outdir}_%s/histogram.json {extra_params}
                    """
                    host_args = [
                        {"cmd": cmd % (i, self.nodes[i].vm.name, self.nodes[i].vm.name)}
                        for i in range(len(self.nodes))
                    ]
                    timeout = (
                        self.kwargs.get("time")
                        + self.kwargs.get("warmup")
                        + EXTRA_BENCHBASE_TIMEOUT
                    )
                    self.logger.info(f"Running repeat {r}, thread: {t}")
                    outputs = self.pssh.run(
                        cmd="%(cmd)s", timeout=timeout, host_args=host_args
                    )
                    # Receiving remote files
                    self.pssh.receive_files(
                        f"/tmp/{remote_outdir}_*/",
                        f"{self.artifact_dir}/",
                        recursive=True,
                    )
                    # Save output locally and replace IP with vm.name
                    for driver, stdout in zip(self.nodes, outputs):
                        output_file: str = os.path.join(
                            self.artifact_dir, f"{outdir}_{driver.vm.name}/stdout"
                        )
                        self.logger.debug(
                            f"Saving {driver.vm.name}'s stdout to {output_file}"
                        )
                        with open(output_file, "w") as output:
                            output.write(stdout["stdout"])
                    # Collect data from each terminal this repeat
                    thread_results = self.one_repeat_overall_results(outdir)
                    this_repeat_results.extend(thread_results)

                    if self.bench in ["tpch", "chbenchmark"]:
                        this_terminal_repeat_queries_results_df = (
                            self.one_repeat_queries_results(r, outdir)
                        )
                        # Let's save queries results. Concurrency is a terminal
                        this_repeat_queries_results[
                            query_terminals
                        ] = this_terminal_repeat_queries_results_df

                    if self.check_errors(
                        outdir, self.kwargs.get("error_threshold")
                    ) or self.check_stdout_errors(outdir):
                        raise BenchmarkException

                # End of all terminals loops for the given repeat. Collect data from each repeat this run
                if self.bench in ["tpch", "chbenchmark"]:
                    self.save_print_queries_one_repeat(this_repeat_queries_results, r)
                    summary_query_data[r] = this_repeat_queries_results

                # Overall summary data
                df = self.save_print_one_repeat(r, this_repeat_results)
                all_results = pd.concat([all_results, df])
        except BenchmarkException as e:
            self.logger.error(f"Benchmark failed")
            success = False
        finally:
            if not success:
                # Save existing data
                if self.bench in ["tpch", "chbenchmark"]:
                    self.save_print_queries_one_repeat(
                        this_repeat_queries_results, repeat_runs
                    )
                    summary_query_data[repeat_runs] = this_repeat_queries_results
                df = self.save_print_one_repeat(repeat_runs, this_repeat_results)
                all_results = pd.concat([all_results, df])

            # End of all repeats loop. Calculate summary data
            if self.bench in ["tpch", "chbenchmark"]:
                self.save_print_queries_summary(summary_query_data)

            self.save_print_summary(all_results)
            if self.kwargs.get("post_workload_run"):
                self.backend.post_workload_run(output_dir=self.artifact_dir)
            if self.kwargs.get("export_query_log"):
                query_log_file: str = os.path.join(self.artifact_dir, "query.log")
                self.logger.debug(f"exporting query log to {query_log_file}")
                with open(query_log_file, "w") as query_log:
                    query_log.write(self.backend.get_logs())
            if not success:
                raise BenchmarkException("Benchmark has errors")

    def check_errors(self, outdir, error_threshold) -> bool:
        """Check the benchbase histogram for unexpected and aborted errors.

        Args:
            outdir (str): Directory to search for histogram jsons
            error_threshold (str): Percentage of errors allowed
        Returns:
            bool: True if error percentage is higher than the given threshold
        """
        aborted_errors = unexpected_errors = completed = 0
        for histogram_json_file in sorted(
            glob(f"{self.artifact_dir}/{outdir}_*/histogram.json")
        ):
            with open(histogram_json_file) as histogram_json:
                data = json.load(histogram_json)
            aborted_errors += data["aborted"]["NUM_SAMPLES"]
            unexpected_errors += data["unexpected"]["NUM_SAMPLES"]
            completed += data["completed"]["NUM_SAMPLES"]
        self.logger.debug(
            f"Aborted Errors: {aborted_errors}, Unexpected Errors: {unexpected_errors},"
            f" Completed Transactions: {completed}"
        )
        error_ratio = (float(aborted_errors + unexpected_errors) / completed) * 100

        if error_ratio > error_threshold:
            self.logger.error(
                f"Percentage of errors ({error_ratio}) exceeds threshold"
                f" ({error_threshold}). Exiting.."
            )
            return True
        else:
            self.logger.debug(f"Percentage of errors = {error_ratio}")
            return False

    def check_stdout_errors(self, outdir) -> bool:
        """Check the stdout of benchbase for Exceptions from Java.

        Args:
            outdir (str): Directory to search for stdout files
        Returns:
            bool: True if a Java error is found
        """
        for stdout_file in sorted(glob(f"{self.artifact_dir}/{outdir}_*/stdout")):
            with open(stdout_file) as stdout:
                for l in stdout:
                    match = re.search(r".+Exception", l)
                    if match:
                        self.logger.warning(f"Java error found in {stdout_file}")
                        return False
        return False

    def save_print_queries_one_repeat(self, dfs: Dict[int, pd.DataFrame], repeat: int):
        """Print and save  Q result

        Args:
            df (Pandas DataFrame):
        """
        self.logger.info(f"======= Benchbase results for repeat {repeat} ==========")
        # All terminals results are in the dictionary so I need first concat them.
        all_dfs: List[pd.DataFrame] = []
        for i in sorted(dfs.keys()):
            df = dfs[i]
            df["concurrency"] = i
            all_dfs.append(df)

        output_string = str(self.summaries_all_queries(all_dfs))
        file_name = os.path.join(
            self.artifact_dir, f"{self.workload_name}_queries_run_{repeat}.csv"
        )
        with open(file_name, "w") as csv_file:
            csv_file.write(output_string)
        self.logger.info(f"Query results for repeat {repeat} saved as {file_name}")

    def summaries_all_queries(self, all_dfs):
        df = pd.concat(all_dfs)

        grouped = df.groupby(["query", "concurrency"]).agg(
            {"avg_latency": ["mean"], "p90_latency": ["max"], "tp": ["mean"]}
        )

        output = grouped.pivot_table(
            index="query",
            columns=["concurrency"],
            values=["avg_latency", "p90_latency", "tp"],
            fill_value=0,
        )

        output.sort_values(
            by="query",
            key=lambda val: val.str.replace("Q", "").astype("int"),
            inplace=True,
        )

        self.logger.info(f"\n{output}")
        return output

    def save_print_queries_summary(self, summary_query_data: Dict[int, Dict]):
        """Print overall summary for queries results after multiple repetitions

        Args:
            summary_query_data (Dict):
        """
        self.logger.info(f"======= Benchbase overall queries result  ==========")
        all_dfs: List[pd.DataFrame] = []
        # For each repeat
        for r, r_terminals in summary_query_data.items():
            # unpack all terminals results
            for k, df in r_terminals.items():
                df["concurrency"] = k
                all_dfs.append(df)

        summary_string = str(self.summaries_all_queries(all_dfs))
        summary_file_name = os.path.join(
            self.artifact_dir, f"{self.workload_name}_queries_summary.csv"
        )
        with open(summary_file_name, "w") as csv_file:
            csv_file.write(summary_string)
        self.logger.info(f"Summary of query results saved as {summary_file_name}")

    def save_print_summary(self, df: pd.DataFrame):
        """Print overall summary for all repeats

        Args:
            df (pd.DataFrame): raw results
        """
        df_summary = df.groupby(["concurrency"]).agg(
            {"throughput": ["mean"], "avg_latency": ["mean"], "p90_latency": ["max"]}
        )
        df_summary.reset_index(inplace=True)
        df_summary.columns = BENCHBASE_RESULT_FIELDS
        df_summary = df_summary.round(RESULT_PRECISION)
        self.logger.info(
            f"======= Overall results ==========\n{df_summary.to_string(index=False)}"
        )
        # And save it
        file_name = os.path.join(self.artifact_dir, f"{self.workload_name}_summary.csv")
        self.logger.info(f"Summary results saved as {file_name}")
        df_summary.to_csv(file_name, index=False)

    def save_print_one_repeat(
        self, repeat: int, repeat_data: List[tuple]
    ) -> pd.DataFrame:
        """Summarize and display benchbase results

        Args:
            repeat (int): The current repeat
            repeat_data (List[tuple]): List of results

        Returns:
            pd.DataFrame: DataFrame grouped by concurrency (terminals)
        """
        df = pd.DataFrame.from_records(repeat_data, columns=BENCHBASE_RESULT_FIELDS)
        df = df.astype(float)
        grouped_multiple = df.groupby("concurrency").agg(
            {
                "throughput": ["sum"],
                "avg_latency": ["mean"],
                "p90_latency": ["max"],
            }
        )
        grouped_multiple.reset_index(inplace=True)
        grouped_multiple.columns = BENCHBASE_RESULT_FIELDS
        grouped_multiple["concurrency"] = self.num_drivers * grouped_multiple[
            "concurrency"
        ].astype(int)
        grouped_multiple["avg_latency"] = grouped_multiple["avg_latency"].astype(float)
        # Final DF
        df_final = grouped_multiple[BENCHBASE_RESULT_FIELDS].round(RESULT_PRECISION)
        self.logger.info(
            f"======= Benchbase results ==========\n{df_final.to_string(index=False)}"
        )
        file_name = os.path.join(
            self.artifact_dir, f"{self.workload_name}_run_{repeat}.csv"
        )
        df_final.to_csv(file_name, index=False)
        df_final["repeat"] = repeat
        self.logger.info(f"Results for repeat {repeat} saved as {file_name}")
        return df_final

    def one_repeat_overall_results(self, outdir):
        """Return total throughput of the repeat. For OLTP this is all we need. For OLAP see also  one_repeat_queries_results

        Args:
            outdir (str): directory where output files are located

        Returns:
            list[tuple]: terminals, throughput, avg_latency, p90_latency

        """
        terminal_data = []
        for summary_json_file in sorted(
            glob(f"{self.artifact_dir}/{outdir}_*/*.summary.json")
        ):
            with open(summary_json_file) as summary_json:
                data = json.load(summary_json)
            terminals = data["terminals"]
            throughput = data["Throughput (requests/second)"]
            avg_latency = round(
                float(data["Latency Distribution"]["Average Latency (microseconds)"])
                / 1000.0,
                2,
            )
            p90_latency = round(
                float(
                    data["Latency Distribution"][
                        "90th Percentile Latency (microseconds)"
                    ]
                )
                / 1000.0,
                2,
            )
            # Collect data from each driver this terminal
            terminal_data.append((terminals, throughput, avg_latency, p90_latency))

        return terminal_data

    # TODO support more than one driver
    def one_repeat_queries_results(self, r, outdir: str) -> pd.DataFrame:
        """Return per query throughput,avg_latency,p90_latency in ms. This applicable to tpch and ch-bench

        Args:
            r (int): repeat
            t (int): current number of terminals

        Returns: query, throughput,avg_latency,p90_latency

        """
        all_cols = [
            "time",
            "throughput",
            "avg_latency",
            "min_latency",
            "p25_latency",
            "p50_latency",
            "p75_latency",
            "p90_latency",
            "p95_latency",
            "p99_latency",
            "max_latency",
            "tp",
        ]
        filter_col = "throughput"
        all_queries: List = []

        for query_file in sorted(
            glob(f"{self.artifact_dir}/{outdir}_*/*.results.Q*.csv")
        ):
            df = pd.read_csv(query_file)
            df.columns = all_cols
            df = df[df[filter_col] > 0]  # not every query run every time

            m = re.match(r".+(Q\d+)\.csv", query_file)
            if m:
                df["query"] = m.group(1)  # Query name, Q1, Q2 etc...
                all_queries.append(
                    df[["query", "tp", "avg_latency", "p90_latency"]]
                )  # this is raw results

        return pd.concat(all_queries)  # all raw results from all queries

    def cleanup(self):
        cmd = """kill -9 $(pgrep -f "jar benchbase.jar") || true"""
        self.run_on_all_nodes(cmd, sudo=True)

    def get_scale_string(self):
        return self.kwargs.get("scale")
