## etcd backup and restore

This section describes the process of backing up and restoring the state of etcd running inside a DC/OS cluster.

Although the etcd cluster is possible to recover from temporary failures and tolerates up to (N-1)/2 permanent failures for a cluster with N members. To recover from a disastrous failure to return a cluster to a healthy state, we need to backup and restore the etcd data. Also when performing maintenance operations, such as an upgrade or downgrade, it's recommended to back up the etcd state before beginning the maintenance.

As only etcd v3 keys require to be stored persistently in DC/OS, only v3 keys are backed up through snapshot and restored in the following process.

### Backing up an etcd cluster

etcd cluster achieves reliable distributed coordination and hence key/value data consistency among all etcd instances, etcd instances on all masters are capable of providing all the key/value data in the current state. As we expose the etcd instance from the Mesos leader node outside to the internal and external clients, it's reasonable to backup the etcd data on the leader node of the DC/OS cluster.

#### Prerequisites

- Make sure there is enough disk space available to temporarily store the etcd backup on a particular master node.
- Any shell commands must be issued as a privileged Linux user.

1. log into the leader node and backup etcd via the following provided script.

`/opt/mesosphere/bin/dcos-shell dcos-etcdctl backup <backup-tar-archive-path>`

2. Download the created etcd backup tar archive from this leader node to a safe location outside of the DC/OS cluster.

3. Remove the etcd backup tar archive from the master node.

## Restoring an etcd cluster 

etcd instance on every master node is required to be restored from the backup file.

1. Copy the previously created single etcd backup tar archive to every master node’s file system.

2. Stop the etcd instances on every master node via the systemd unit.
`systemctl stop dcos-etcd`

3. Initiate the restore procedure via the provided DC/OS etcd restore script on every master node.

`/opt/mesosphere/bin/dcos-shell dcos-etcdctl restore <backup-tar-archive-path>`

4. Start the previously stopped etcd instances again on every master node.

`systemctl start dcos-etcd`

5. Check the etcd cluster status.

`/opt/mesosphere/bin/dcos-shell dcos-etcdctl diagnostic`

the expected result is that all the etcd instances on all masters are listed according to `member list -w json`
Validate a path does not exist but the parent directory tree exists
