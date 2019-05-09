#!/usr/bin/env bash
set -euxo pipefail

SSH_USER='root'
REMOTE_TMP_DIR=/tmp

usage() {
  echo "Usage: $0 [-h] [-l SSH_USER] [-i SSH_KEY_PATH] [-t REMOTE_TMP_DIR] ZK_BACKUP_PATH MASTER_HOSTNAME..." 1>&2
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
if (($# < 2)); then
  exit_abnormal
fi

BACKUP_PATH=$1
REMOTE_BACKUP_DIR=${REMOTE_TMP_DIR}/zk_backup.$$
OPTS='-o ConnectTimeout=3 -o ConnectionAttempts=1
-o UserKnownHostsFile=/dev/null -o StrictHostKeyChecking=no'
KEY=${SSH_KEY_PATH:+"-i $SSH_KEY_PATH"}

shift

for i in "$@"
do
ssh $OPTS -tt $KEY ${SSH_USER}@${i} << EOF
  set -euxo pipefail
  if [ -d "$REMOTE_BACKUP_DIR" ]; then
    exit 1
  fi
  sudo mkdir -p $REMOTE_BACKUP_DIR
  sudo systemctl stop dcos-exhibitor
  exit 0
EOF
scp $OPTS $KEY $BACKUP_PATH $SSH_USER@${i}:${REMOTE_BACKUP_DIR}/zk_backup.tar.gz 2> /dev/null
done

for i in "$@"
do
ssh $OPTS -tt $KEY ${SSH_USER}@${i} << EOF
  set -euxo pipefail
  sudo mv /var/lib/dcos/exhibitor/zookeeper ${REMOTE_BACKUP_DIR}/zookeeper.old
  sudo tar -C /var/lib/dcos/exhibitor --same-owner -xzvf ${REMOTE_BACKUP_DIR}/zk_backup.tar.gz
  sudo systemctl start dcos-exhibitor
  exit 0
EOF
done

for i in "$@"
do
ssh $OPTS -tt $KEY ${SSH_USER}@${i} << EOF
  set -euxo pipefail
  sudo rm -rf $REMOTE_BACKUP_DIR
  exit 0
EOF
done
