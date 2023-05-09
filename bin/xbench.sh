#!/usr/bin/env bash

XBENCH_HOME=$(cd "$(dirname "${BASH_SOURCE[0]}")" && cd ../ && pwd)
PYTHONPATH=${XBENCH_HOME}
PATH=${XBENCH_HOME}/bin:/usr/local/bin:$PATH

set -f # Disable shell globbing. Required to run external commands (sql may contains *)

# XBENCH config file
if [ -f ${HOME}/.xbench/xbench_config.yaml ]; then
    XBENCH_CONFIG=${HOME}/.xbench/xbench_config.yaml
else
    XBENCH_CONFIG=${XBENCH_HOME}/xbench_config.yaml
fi

# Default options. If envsubst installed you could use enviroment variables in xbench_options
foo=$(which envsubst)
[[ -z $foo ]] && foo='cat'

OPTIONS_FILE=$HOME/.xbench/xbench_options
if [ -f $OPTIONS_FILE ]; then
    DEFAULT_OPTIONS=$($foo <"$OPTIONS_FILE")
fi

if [[ ! -z ${CLUSTER} ]]; then
    ENV_OPTIONS="--cluster ${CLUSTER}"
fi

export XBENCH_HOME XBENCH_CONFIG PYTHONPATH PATH
cd $XBENCH_HOME

CMD=$1
shift

PYTHON=python3.9
$PYTHON bin/xb.py $CMD $ENV_OPTIONS $DEFAULT_OPTIONS $@
