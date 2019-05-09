#!/usr/bin/env bash
set -euxo pipefail

SSH_USER='root'
REMOTE_TMP_DIR=/tmp

usage() {
  echo "Usage: $0 [-h] [-l SSH_USER] [-i SSH_KEY_PATH] [-t REMOTE_TMP_DIR] ZK_BACKUP_DEST_DIR MASTER_HOSTNAME" 1>&2
}
exit_abnormal() {
  usage
  exit 1
}
while getopts ":hl:i:t:" opt; do
  case $opt in
    h)
      usage
      exit 0
    ;;
    l) SSH_USER=$OPTARG
    ;;
    i) SSH_KEY_PATH=$OPTARG
    ;;
    t) REMOTE_TMP_DIR=$OPTARG
    ;;
    \?) echo "Error: Invalid option -$OPTARG" 1>&2
        exit_abnormal
    ;;
    :) echo "Error: -$OPTARG requires an argument." 1>&2
       exit_abnormal
    ;;
    *) exit_abnormal
    ;;
  esac
done

shift $((OPTIND - 1))
if (($# != 2)); then
  exit_abnormal
fi

DESTINATION_DIR=$1
if [ ! -d "$DESTINATION_DIR" ]; then
  echo "Error: $DESTINATION_DIR does not exist." 1>&2
  exit 1
fi

MASTER_HOST=$2
REMOTE_BACKUP_DIR=${REMOTE_TMP_DIR}/zk_backup.$$
KEY=${SSH_KEY_PATH:+"-i $SSH_KEY_PATH"}
OPTS='-o ConnectTimeout=3 -o ConnectionAttempts=1
-o UserKnownHostsFile=/dev/null -o StrictHostKeyChecking=no'

ssh $OPTS $KEY -tt ${SSH_USER}@${MASTER_HOST} << EOF
  set -exo pipefail
  if [ -d "$REMOTE_BACKUP_DIR" ]; then
    exit 1
  fi
  mkdir -p $REMOTE_BACKUP_DIR
  sudo systemctl stop dcos-exhibitor
  sudo cp -pr /var/lib/dcos/exhibitor/zookeeper ${REMOTE_BACKUP_DIR}/zookeeper
  sudo systemctl start dcos-exhibitor
  sudo tar --exclude 'myid' --exclude 'zookeeper.out' -pcvzf \\
  ${REMOTE_BACKUP_DIR}/zk_backup-'$(date +%Y-%m-%d_%H-%M-%S)'.tar.gz -C $REMOTE_BACKUP_DIR ./zookeeper
  sudo rm -rf ${REMOTE_BACKUP_DIR}/zookeeper
  exit 0
EOF

scp $OPTS $KEY -r ${SSH_USER}@${MASTER_HOST}:${REMOTE_BACKUP_DIR}/zk_backup-'*'.tar.gz ${DESTINATION_DIR}/ 2> /dev/null

ssh $OPTS $KEY -tt ${SSH_USER}@${MASTER_HOST} << EOF
  set -exo pipefail
  sudo rm -rf $REMOTE_BACKUP_DIR
  exit 0
EOF
