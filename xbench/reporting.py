# -*- coding: utf-8 -*-
# Copyright (C) 2021 dvolkov

import os
from typing import Optional

from compute import ProcessExecutionException, RunSubprocess

from .exceptions import XbenchException
from .xbench import Xbench

PAPERMILL_TIMEOUT=300
NOTEBOOK="xbench.ipynb"

class Reporting(Xbench):
    """Main class to run workload"""

    def __init__(
        self,
        cluster_name,
        benchmark_name: str,
        artifact_dir: str,
        yaml_config: Optional[str],
        notebook_name: Optional[str] = "results",
        notebook_title: Optional[str] = "Test results"
    ):
        super(Reporting, self).__init__(cluster_name)
        self.cluster_name = cluster_name
        self.benchmark_name = benchmark_name
        # Reporting could get artifact directory after workload (run command only)
        self.artifact_dir = os.path.join(artifact_dir, cluster_name) if cluster_name not in artifact_dir else artifact_dir
        self.yaml_config = yaml_config
        self.notebook_name = notebook_name
        self.notebook_title = notebook_title

    # TODO
    #  jupyter nbconvert $XBENCH_HOME/notebooks/{self.notebook_name}.ipynb --execute --no-input --to html --output $bname.html

    def run(self):
        self.logger.info('Reporting has started')
        report_notebook = f"notebooks/{NOTEBOOK}" # I am in XBENCH_HOME directory (xbench.sh does it for me)
        final_notebook_name = os.path.join(self.artifact_dir,f"{self.notebook_name}.ipynb")
        config_file_clause = f"-p yaml_config_file_name {self.yaml_config}" if self.yaml_config is not None else ""
        title_clause = f"-p title '{self.notebook_title}'" if self.notebook_title is not None else ""
        cmd = f"""
        papermill {config_file_clause} {title_clause} -p search_path {self.artifact_dir} -p benchmark {self.benchmark_name} {report_notebook} {final_notebook_name}
        """
        try:
            self.logger.debug(cmd)
            proc = RunSubprocess(cmd=cmd, timeout=PAPERMILL_TIMEOUT)
            (stdout, stderr, exit_code) = proc.run_as_shell()
            self.logger.info(f"Final notebook is {final_notebook_name}")
        except ProcessExecutionException as e:
            raise XbenchException(e)
