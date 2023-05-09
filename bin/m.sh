#!/usr/bin/env bash
# Usage: m.sh backend_0 # will run mariadDB and conect to the cluster
# yq is from https://github.com/mikefarah/yq
member=$1
shift
CLUSTER=${CLUSTER:-dsv_cluster}
user=$(yq ".bt.user" $HOME/.xbench/clusters/$CLUSTER.yaml)
password=$(yq ".bt.password" $HOME/.xbench/clusters/$CLUSTER.yaml)
host=$(yq ".bt.host" $HOME/.xbench/clusters/$CLUSTER.yaml)
port=$(yq ".bt.port" $HOME/.xbench/clusters/$CLUSTER.yaml)
database=$(yq ".bt.database" $HOME/.xbench/clusters/$CLUSTER.yaml)
public_ip=$(yq ".members.$member.network.public_ip" $HOME/.xbench/clusters/$CLUSTER.yaml)
DATABASE=${DATABASE:-$database}
if [ -z "$@" ]; then
    mariadb -u $user --password=$password --port $port --host=$public_ip --database=$DATABASE
else
    mariadb -u $user --password=$password --port $port --host=$public_ip --database=$DATABASE -e "$@"
fi
