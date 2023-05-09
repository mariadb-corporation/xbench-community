#!/usr/bin/env bash
# Describe the cluster
# Usage: d.sh
# yq is from https://github.com/mikefarah/yq

xbench_config() {
  python3.9 -c "from lib import XbenchConfig; XbenchConfig().initialize(); xb = XbenchConfig().get_config(); print (xb.get('$1'))"
}

member=$1
CLUSTER=${CLUSTER:-$1}
CLUSTERS_DIR=$(xbench_config clusters_dir)
#
yq ' .members | to_entries | .[] | [.key, .value.network.public_ip,.value.network.private_ip] | join(",")' ${CLUSTERS_DIR}/$CLUSTER.yaml
