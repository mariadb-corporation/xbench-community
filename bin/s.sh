#!/usr/bin/env bash
# Usage: s.sh driver_0
# yq is from https://github.com/mikefarah/yq
#set -x

xbench_config() {
  python3.9 -c "from lib import XbenchConfig; XbenchConfig().initialize(); xb = XbenchConfig().get_config(); print (xb.get('$1'))"
}

member=$1
cmd=$2
CLUSTER=${CLUSTER:-dsv_cluster}
PEM_DIR=$(xbench_config pem_dir)
CLUSTERS_DIR=$(xbench_config clusters_dir)
#
ssh_opts='-o StrictHostKeyChecking=no -o LogLevel=ERROR'
public_ip=$(yq ".members.$member.network.public_ip" ${CLUSTERS_DIR}/$CLUSTER.yaml)
user=$(yq ".members.$member.ssh_user" ${CLUSTERS_DIR}/$CLUSTER.yaml)
if [[ -z $cmd ]]; then
  ssh -i ${PEM_DIR}/xbench.pem $ssh_opts $user@$public_ip
else
  ssh -i ${PEM_DIR}/xbench.pem $ssh_opts $user@$public_ip "${cmd}"
fi
