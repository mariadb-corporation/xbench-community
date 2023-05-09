#!/usr/bin/env bash
# Usage: s.sh driver_0
# yq is from https://github.com/mikefarah/yq
set -x

member=$1
fname=$2
CLUSTER=${CLUSTER:-dsv_cluster}
echo $CLUSTER
public_ip=$(yq ".members.$member.network.public_ip" $HOME/.xbench/clusters/$CLUSTER.yaml)
user=$(yq ".members.$member.ssh_user" $HOME/.xbench/clusters/$CLUSTER.yaml)
ssh_opts='-o StrictHostKeyChecking=no'
scp -i $HOME/.xbench/pem/xbench.pem $ssh_opts $fname $user@$public_ip:~
