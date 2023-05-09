#!/usr/bin/env bash

# Provision cluster
function provision() {

    [ ! -z ${LOG_DIR} ] && logdir_clause="--log-dir ${LOG_DIR}" || logdir_clause=""
    [ ! -z ${LOG_LEVEL} ] && loglevel_clause="--log-level ${LOG_LEVEL}" || loglevel_clause=""
    [ ! -z ${ARTIFACT_DIR} ] && artifact_dir_clause="--artifact-dir ${ARTIFACT_DIR}" || artifact_dir_clause=""
    [ ! -z ${IMPL} ] && impl_clause="--impl ${IMPL}" || impl_clause=""

    $XBENCH_HOME/bin/xbench.sh p --cluster ${CLUSTER} --topo ${TOPO} $impl_clause $logdir_clause $loglevel_clause $artifact_dir_clause $@

}

# Populate data set
function prepare() {

    [ ! -z ${LOG_DIR} ] && logdir_clause="--log-dir ${LOG_DIR}" || logdir_clause=""
    [ ! -z ${LOG_LEVEL} ] && loglevel_clause="--log-level ${LOG_LEVEL}" || loglevel_clause=""
    [ ! -z ${ARTIFACT_DIR} ] && artifact_dir_clause="--artifact-dir ${ARTIFACT_DIR}" || artifact_dir_clause=""

    $XBENCH_HOME/bin/xbench.sh w --cluster $CLUSTER -b ${BENCHMARK} -w ${WORKLOAD} $logdir_clause $loglevel_clause $artifact_dir_clause --step prepare $@

}

# Run sql command
function sqlcli() {
    $XBENCH_HOME/bin/m.sh $1 "$2"

}
function test() {

    [ ! -z ${LOG_DIR} ] && logdir_clause="--log-dir ${LOG_DIR}" || logdir_clause=""
    [ ! -z ${LOG_LEVEL} ] && loglevel_clause="--log-level ${LOG_LEVEL}" || loglevel_clause=""
    [ ! -z ${ARTIFACT_DIR} ] && artifact_dir_clause="--artifact-dir ${ARTIFACT_DIR}" || artifact_dir_clause=""

    $XBENCH_HOME/bin/xbench.sh w --cluster $CLUSTER -b ${BENCHMARK} -w ${WORKLOAD} $logdir_clause $loglevel_clause $artifact_dir_clause --step test $@

}

function run() {

    [ ! -z ${LOG_DIR} ] && logdir_clause="--log-dir ${LOG_DIR}" || logdir_clause=""
    [ ! -z ${LOG_LEVEL} ] && loglevel_clause="--log-level ${LOG_LEVEL}" || loglevel_clause=""
    [ ! -z ${ARTIFACT_DIR} ] && artifact_dir_clause="--artifact-dir ${ARTIFACT_DIR}" || artifact_dir_clause=""

    $XBENCH_HOME/bin/xbench.sh w --cluster $CLUSTER -b ${BENCHMARK} -w ${WORKLOAD} $logdir_clause $loglevel_clause $artifact_dir_clause --step test $@
    $XBENCH_HOME/bin/xbench.sh w --cluster $CLUSTER -b ${BENCHMARK} -w ${WORKLOAD} $logdir_clause $loglevel_clause $artifact_dir_clause --step run $@

}

function run_only() {

    [ ! -z ${LOG_DIR} ] && logdir_clause="--log-dir ${LOG_DIR}" || logdir_clause=""
    [ ! -z ${LOG_LEVEL} ] && loglevel_clause="--log-level ${LOG_LEVEL}" || loglevel_clause=""
    [ ! -z ${ARTIFACT_DIR} ] && artifact_dir_clause="--artifact-dir ${ARTIFACT_DIR}" || artifact_dir_clause=""

    $XBENCH_HOME/bin/xbench.sh w --cluster $CLUSTER -b ${BENCHMARK} -w ${WORKLOAD} $logdir_clause $loglevel_clause $artifact_dir_clause --step run $@

}

function restore() {

    [ ! -z ${LOG_DIR} ] && logdir_clause="--log-dir ${LOG_DIR}" || logdir_clause=""
    [ ! -z ${LOG_LEVEL} ] && loglevel_clause="--log-level ${LOG_LEVEL}" || loglevel_clause=""
    [ ! -z ${ARTIFACT_DIR} ] && artifact_dir_clause="--artifact-dir ${ARTIFACT_DIR}" || artifact_dir_clause=""
    [ ! -z ${BACKUP_TAG} ] && backup_clause="--tag ${BACKUP_TAG}" || backup_clause=""

    $XBENCH_HOME/bin/xbench.sh w --cluster $CLUSTER -b ${BENCHMARK} -w ${WORKLOAD} $logdir_clause $loglevel_clause $artifact_dir_clause $backup_clause --step restore $@
}

# De-provision cluster
function deprovision() {

    [ ! -z ${LOG_DIR} ] && logdir_clause="--log-dir ${LOG_DIR}" || logdir_clause=""
    [ ! -z ${LOG_LEVEL} ] && loglevel_clause="--log-level ${LOG_LEVEL}" || loglevel_clause=""
    [ ! -z ${ARTIFACT_DIR} ] && artifact_dir_clause="--artifact-dir ${ARTIFACT_DIR}" || artifact_dir_clause=""

    $XBENCH_HOME/bin/xbench.sh d --cluster $CLUSTER $logdir_clause $loglevel_clause $artifact_dir_clause $@

}

function simple_report() {
    # $1 is an experiment name
    bname=$(basename -s .sh $1)
    shift
    $XBENCH_HOME/bin/xbench.sh report --cluster $CLUSTER -b ${BENCHMARK} --notebook-name $bname $@
}

function yaml_report() {
    # $1 is an experiment name
    bname=$(basename -s .sh $1)
    shift
    $XBENCH_HOME/bin/xbench.sh report --cluster $CLUSTER -b ${BENCHMARK} --notebook $bname --yaml-config experiments/$bname.yaml
}

# Clean up after the error in the script execution
function cleanup() {

    $XBENCH_HOME/bin/xbench.sh d --cluster $CLUSTER --cloud $1 --region $2 --force

}
