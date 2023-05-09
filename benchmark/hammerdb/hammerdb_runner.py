import os
import re
import time
from datetime import datetime
from glob import glob
from typing import List

from benchmark.abstract_benchmark import AbstractBenchmarkRunner
from benchmark.exceptions import BenchmarkException
from common.common import get_class_from_klass
from compute import MultiNode, Node
from lib.file_template import FileTemplate, FileTemplateException

DEFAULT_COMMAND_TIMEOUT = 300
DEFAULT_SLEEP_TIME = 60  # sleep time between threads

PRODUCT_PREFIX = {
    "oracle": "ora",
    "mssql": "mssqls",
    "mysql": "mysql",
    "aurora-mysql": "mysql",
    "postgres": "pg",
    "aurora-postgres": "pg",
    "mariadb": "maria",
    "xpand": "maria",
}


class HammerdbRunner(MultiNode, AbstractBenchmarkRunner):
    """Run HammerDB on driver(s)"""

    def __init__(self, nodes: List[Node], **kwargs):
        """Implements HammerDB

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
        self.product = self.kwargs.get("product")
        self.phase = ""

        # hammerdb takes time args in minutes and must be int greater than 0
        self.warmup_m = int(self.kwargs.get("warmup") / 60)
        self.warmup_m = 1 if self.warmup_m < 1 else self.warmup_m
        self.time_m = int(self.kwargs.get("time") / 60)
        self.time_m = 1 if self.time_m < 1 else self.time_m
        self.totaltime = 60 * (self.warmup_m + self.time_m)

    def get_script(self, virtusers) -> str:
        try:
            ft = FileTemplate(filename=f"hammerdb.tcl")
            hosts = (",").join([host for host in self.kwargs.get("host").split(",")])
            prefix = PRODUCT_PREFIX[self.product]
            render = ft.render(
                **self.kwargs
                | {
                    "hosts": hosts,
                    "password": self.kwargs.get("password"),
                    "prefix": prefix,
                    "virtusers": virtusers,
                    "phase": self.phase,
                    "warmup_m": self.warmup_m,
                    "time_m": self.time_m,
                    "totaltime": self.totaltime,
                }
            )
        except FileTemplateException as e:
            raise BenchmarkException(e)

        return render

    def parse_timeprofile(self, log_file):
        throughput, avg_lat, p95_lat = 0, 0, 0
        calls, total, p95 = {}, {}, {}
        with open(log_file, "r") as lines:
            summary = False
            proc = ""
            for line in lines:
                if re.search("SUMMARY", line):
                    summary = True
                elif summary:
                    m = re.match("\S+ PROC: (?P<proc>\S+)", line)
                    if m:
                        proc = m.groupdict()["proc"]
                        #print(proc)
                    m = re.match(
                        "CALLS: (?P<calls>\d+)\s*MIN: (?P<min>\d+[\.\d]*)ms\s*AVG:"
                        " (?P<avg>\d+[\.\d]*)ms\s*MAX: (?P<max>\d+[\.\d]*)ms\s*TOTAL:"
                        " (?P<total>\d+[\.\d]*)ms",
                        line,
                    )
                    if m:
                        calls[proc] = int(m.groupdict()["calls"])
                        total[proc] = float(m.groupdict()["total"])
                    m = re.match(
                        "P99: (?P<p99>\d+[\.\d]*)ms\s*P95: (?P<p95>\d+[\.\d]*)ms\s*P50:"
                        " (?P<p50>\d+[\.\d]*)ms\s*SD: (?P<sd>\d+[\.\d]*)\s*RATIO:"
                        " (?P<ratio>\d+[\.\d]*)",
                        line,
                    )
                    if m:
                        p95[proc] = calls[proc] * float(m.groupdict()["p95"])
        throughput = sum(calls[p] for p in calls) / self.totaltime
        avg_lat = sum(total[p] for p in total) / sum(calls[p] for p in calls)
        p95_lat = sum(p95[p] for p in p95) / sum(calls[p] for p in calls)
        print(f"throughput: {throughput}, avg lat: {avg_lat}, p95 lat: {p95_lat}")
        return throughput, avg_lat, p95_lat

    def prepare(self):
        self.phase = "load"
        warehouses = self.kwargs.get("warehouses")
        num_vu_load = self.kwargs.get("num_vu_load")
        self.logger.info(f"Loading {warehouses} warehouses with {num_vu_load} virtual users")
        load_script = self.get_script(0)
        prepare_cmd = f"""
        cd $XBENCH_HOME/HammerDB
        echo \"{load_script}\" > load.tcl
        ./hammerdbcli auto load.tcl
        """
        output = self.head_node._unsafe_run(prepare_cmd)
        self.logger.debug(output)
        if self.kwargs.get("post_data_load"):
            self.backend.post_data_load(
                database=self.kwargs.get("database")
            )  # This uses the fact that workload.py pass it to runner class
        self.logger.info("Load complete")

    def run(self):
        self.phase = "run"
        num_vu = (
            [self.kwargs.get("num_vu")]
            if isinstance(self.kwargs.get("num_vu"), int)
            else self.kwargs.get("num_vu")
        )
        repeats = self.kwargs.get("repeats")
        num_drivers = len(self.nodes)
        now = datetime.now().strftime("%Y%m%d_%H%M%S")
        run_outdir = f"/tmp/{now}_hammerdb_{self.bench}"
        self.logger.info(f"Using {num_drivers} drivers to generate load")
        summary_data = {}
        for r in range(1, repeats + 1):
            if self.kwargs.get("pre_workload_run"):
                self.backend.pre_workload_run()
            repeat_data = {}
            for v in num_vu:
                time.sleep(DEFAULT_SLEEP_TIME)
                if self.kwargs.get("pre_thread_run"):
                    self.backend.pre_thread_run()
                per_driver_v = int(v / num_drivers)
                outdir = f"{run_outdir}/{v}_vu_run_{r}"
                run_script = self.get_script(per_driver_v)
                run_cmd = f"""
                cd $XBENCH_HOME/HammerDB
                echo \"{run_script}\" > run.tcl
                mkdir -p {run_outdir}
                ./hammerdbcli auto run.tcl > {outdir}_%s.out
                if test -f /tmp/hdbtcount.log; then
                    mv /tmp/hdbtcount.log {outdir}_hdbtcount_%s.log
                fi
                if test -f /tmp/hdbxtprofile.log; then
                    mv /tmp/hdbxtprofile.log {outdir}_hdbxtprofile_%s.log
                fi
                """
                host_args = [
                    {
                        "cmd": run_cmd
                        % (
                            self.nodes[i].vm.name,
                            self.nodes[i].vm.name,
                            self.nodes[i].vm.name,
                        )
                    }
                    for i in range(len(self.nodes))
                ]
                timeout = self.kwargs.get("time") + self.kwargs.get("warmup") + 600
                self.logger.info(f"Running repeat {r}, thread: {v}")
                self.pssh.run(cmd="%(cmd)s", timeout=timeout, host_args=host_args)
                self.pssh.receive_files(
                    f"{run_outdir}/*", f"{self.artifact_dir}/", recursive=True
                )
                vu_data = []
                for timeprofile_log in sorted(
                    glob(f"{self.artifact_dir}/{v}_vu_run_{r}_hdbxtprofile_*.log")
                ):
                    (
                        throughput,
                        avg_latency,
                        p95_latency,
                    ) = self.parse_timeprofile(timeprofile_log)

                    # Collect data from each driver this terminal
                    vu_data.append(
                        {
                            "throughput": throughput,
                            "avg_latency": avg_latency,
                            "p95_latency": p95_latency,
                        }
                    )

                vu_throughput = sum([data["throughput"] for data in vu_data])
                print(f"vu_data length = {vu_data}")
                vu_avg_latency = sum([data["avg_latency"] for data in vu_data]) / len(
                    vu_data
                )
                vu_p95_latency = max(data["p95_latency"] for data in vu_data)
                # Collect data from each terminal this repeat
                repeat_data[v] = {
                    "throughput": vu_throughput,
                    "avg_latency": vu_avg_latency,
                    "p95_latency": vu_p95_latency,
                }
            # Collect data from each repeat this run
            summary_data[r] = repeat_data
            self.logger.info("======= HammerDB results ==========")
            output_string = f"concurrency,throughput,avg_latency,p95_latency\n"
            for t, data in repeat_data.items():
                output_string = f'{output_string}{v},{data["throughput"]},{data["avg_latency"]},{data["p95_latency"]}\n'
            self.logger.info(output_string)
            file_name = os.path.join(
                self.artifact_dir, f"{self.workload_name}_run_{r}.csv"
            )
            with open(file_name, "w") as csv_file:
                csv_file.write(output_string)
            self.logger.info(f"Results for repeat {r} saved as {file_name}")
        # Calculate summary data
        self.logger.info("======= Overall results ==========")
        summary_string = f"concurrency,throughput,avg_latency,p95_latency\n"
        for v in num_vu:
            summary_throughput = (
                sum(summary_data[r][v]["throughput"] for r in range(1, repeats + 1))
                / repeats
            )
            summary_avg_latency = (
                sum(summary_data[r][v]["avg_latency"] for r in range(1, repeats + 1))
                / repeats
            )
            summary_p95_latency = max(
                summary_data[r][v]["p95_latency"] for r in range(1, repeats + 1)
            )
            summary_string = f"{summary_string}{v},{summary_throughput},{summary_avg_latency},{summary_p95_latency}\n"
        self.logger.info(summary_string)
        summary_file_name = os.path.join(
            self.artifact_dir, f"{self.workload_name}_summary.csv"
        )
        with open(summary_file_name, "w") as csv_file:
            csv_file.write(summary_string)
        self.logger.info(f"Results for repeat {r} saved as {summary_file_name}")

    def get_scale_string(self):
        return self.kwargs.get("warehouses")

    def data_check(self):
        # TODO: implement data check for hammerdb schemas
        pass

    def cleanup(self):
        cmd = """kill -9 $(pgrep -f "hammerdbcli") || true"""
        self.run_on_all_nodes(cmd, sudo=True)
            

