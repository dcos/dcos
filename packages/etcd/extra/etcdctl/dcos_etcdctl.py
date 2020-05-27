#!/usr/bin/env python

import argparse
import json
import os
import shlex
import shutil
import subprocess
import sys
import tarfile
import tempfile
from argparse import ArgumentTypeError
from pathlib import Path

import requests


ETCD_DATA_DIR = "/var/lib/dcos/etcd/default.etcd"
CLUSTER_NODES_PATH = "/var/lib/dcos/etcd/initial-nodes"
CLUSTER_STATE_PATH = "/var/lib/dcos/etcd/initial-state"


def run_command(cmd: str,
                verbose: bool = False,
                env: dict={}) -> subprocess.CompletedProcess:
    """ Run a command in a subprocess.

    Args:
        verbose: Show the output.

    Raises:
        subprocess.CalledProcessError: The given cmd exits with a non-0 exit
                                       code.
    """
    stdout = None if verbose else subprocess.PIPE
    stderr = None if verbose else subprocess.STDOUT
    p = subprocess.run(
        args=shlex.split(cmd),
        stdout=stdout,
        stderr=stderr,
        encoding='utf-8',
        check=True,
        env=env,
    )
    return p


def detect_ip():
    cmd = '/opt/mesosphere/bin/detect_ip'
    ret = run_command(cmd)
    machine_ip = ret.stdout.strip()
    return machine_ip


def non_existing_file_path_existing_parent_dir(value: str) -> Path:
    """Validate a path does not exist but its parent directory tree exists."""
    path = Path(value)
    if path.exists():
        raise ArgumentTypeError('{} already exists'.format(path))
    if not Path(path.parent).exists():
        raise ArgumentTypeError(
            '{} parent directory does not exist'.format(path))
    return path.absolute()


def existing_file_path(value: str) -> Path:
    """Validate that the value is a file existing on the file system."""
    path = Path(value)
    if not path.exists():
        raise argparse.ArgumentTypeError('{} does not exist'.format(path))
    if not path.is_file():
        raise argparse.ArgumentTypeError('{} is not a file'.format(path))
    return path.absolute()


class EtcdExecutorCommon():

    def __init__(self):
        self.etcdctl_path = "/opt/mesosphere/bin/etcdctl"
        self.private_ip = detect_ip()
        self.master_ip = "master.dcos.thisdcos.directory"

    def log_cmd_result(self, cmd: str, p: subprocess.CompletedProcess) -> None:
        def _sanitize_output(output):
            if output is None:
                return output
            return output.strip()

        print(
            "cmd `{}`, exit status: `{}`, stdout: `{}`, stderr: `{}`\n".format(
                cmd, p.returncode, _sanitize_output(p.stdout),
                _sanitize_output(p.stderr)))

    def get_endpoint(self, scheme, user_master_endpoint) -> str:
        endpoint_ip = self.private_ip
        if user_master_endpoint:
            endpoint_ip = self.master_ip
        endpoint = "{}://{}:2379".format(scheme, endpoint_ip)
        return endpoint


class EtcdExecutorSecure(EtcdExecutorCommon):

    def __init__(self) -> None:
        super(EtcdExecutorSecure, self).__init__()
        self.ca_cert_file = "/run/dcos/pki/CA/ca-bundle.crt"
        self.cert_file = "/run/dcos/pki/tls/certs/etcd-client-root.crt"
        self.key_file = "/run/dcos/pki/tls/private/etcd-client-root.key"
        self.scheme = "https"

    def execute(
            self,
            args: str,
            user_master_endpoint: bool=True,
            use_v3: bool = False,
    ) -> subprocess.CompletedProcess:
        cmd = self.etcdctl_path
        endpoint = self.get_endpoint(self.scheme, user_master_endpoint)
        cmd = "{} --endpoints={}".format(cmd, endpoint)
        cmd = "{} --cacert={} --cert={} --key={}".format(
            cmd, self.ca_cert_file, self.cert_file, self.key_file)
        cmd = "{} {}".format(cmd, args)
        env = {} if not use_v3 else {"ETCDCTL_API": "3"}
        result = run_command(cmd, env=env)

        self.log_cmd_result(args, result)

        return result


class EtcdExecutorInsecure(EtcdExecutorCommon):
    def __init__(self) -> None:
        super(EtcdExecutorInsecure, self).__init__()
        self.scheme = "http"

    def execute(
            self,
            args: str,
            user_master_endpoint: bool=True,
            use_v3: bool = False,
    ) -> subprocess.CompletedProcess:
        cmd = self.etcdctl_path
        endpoint = self.get_endpoint(self.scheme, user_master_endpoint)
        cmd = "{} --endpoints={}".format(cmd, endpoint)
        cmd = "{} {}".format(cmd, args)
        env = {} if not use_v3 else {"ETCDCTL_API": "3"}
        result = run_command(cmd, env=env)
        self.log_cmd_result(args, result)

        return result


class EtcdCmdBase():

    def __init__(self) -> None:
        self.supported_cmd = []
        self.executor = EtcdExecutorInsecure()
        if self.is_dcos_ee():
            self.executor = EtcdExecutorSecure()

    def is_dcos_ee(self) -> bool:
        # This is the expanded DC/OS configuration JSON document w/o sensitive
        # values. Read it, parse it.
        dcos_cfg_path = '/opt/mesosphere/etc/expanded.config.json'
        with open(dcos_cfg_path, 'rb') as f:
            dcos_config = json.loads(f.read().decode('utf-8'))
        dcos_variant = dcos_config.get("dcos_variant")
        return True if dcos_variant == "enterprise" else False

    def execute_etcdctl(
            self,
            args: str,
            user_master_endpoint: bool=True,
            use_v3: bool = False,
    ) -> subprocess.CompletedProcess:
        return self.executor.execute(args, user_master_endpoint, use_v3)


class EtcdBackupAndRestore(EtcdCmdBase):
    """backup and restore V3 key data of etcd."""

    SNAPSHOT_NAME = "etcd_snapshot.db"

    def __init__(self) -> None:
        super(EtcdBackupAndRestore, self).__init__()
        self.supported_cmd = ["backup", "restore"]
        self.scheme = "https" if self.is_dcos_ee() else "http"

    def backup(self) -> None:
        parser = argparse.ArgumentParser(
            usage='{} backup [-h] backup_path'.format(sys.argv[0]),
            description='Create a backup of the etcd instance running on this '
                        'DC/OS master node.')
        parser.add_argument(
            'backup_path',
            type=non_existing_file_path_existing_parent_dir,
            help='File path that the gzipped etcd backup tar archive '
                 'will be written to',
        )
        args = parser.parse_args(sys.argv[2:])
        print("Backing up etcd into {}".format(args.backup_path))
        with tempfile.TemporaryDirectory(suffix="-back-etcd") as tmp_dir:
            snapshot_file = os.path.join(tmp_dir, self.SNAPSHOT_NAME)
            self.execute_etcdctl("snapshot save {}".format(snapshot_file))
            with tarfile.open(name=args.backup_path, mode='x:gz') as tar:
                tar.add(name=snapshot_file, arcname=self.SNAPSHOT_NAME)
        print("etcd snaptshot is archieved under {}".format(args.backup_path))

    def restore(self) -> None:
        """ restore etcd cluster from backup file

        all etcd cluster members are required to be restored through the backup
        snapshot, that means etcd restore command should be executed on all
        masters.

        a command example of restoring a etcd node:
        ETCDCTL_API=3 etcdctl snapshot restore snapshot.db \
          --name m1 \
          --data-dir= /path/to/store_data \
          --initial-cluster m1=http://host1:2380,m2=http://host2:2380,m3=http://host3:2380 \
          --initial-cluster-token etcd-dcos \
          --initial-advertise-peer-urls http://host1:2380

        reference: https://github.com/etcd-io/etcd/blob/master/Documentation/op-guide/recovery.md # NOQA
        """

        def _get_master_ips():
            """ returns IP addresses of master nodes """
            master_ip_url = "http://127.0.0.1:8123/v1/hosts/master.mesos"
            resp = requests.get(master_ip_url, timeout=10)
            if resp.status_code != 200:
                resp.raise_for_status()

            host_ip_list = resp.json()
            master_ips = [host_ip["ip"] for host_ip in host_ip_list]
            return master_ips

        parser = argparse.ArgumentParser(
            description='restore etcd cluster from an archieved file')
        parser.add_argument(
            'backup_path',
            type=existing_file_path,
            help='File path to the gzipped ZooKeeper backup tar archive to '
                 'restore from.',
        )
        args = parser.parse_args(sys.argv[2:])

        # remove the data directory if exists
        try:
            shutil.rmtree(ETCD_DATA_DIR)
            print("The original data path {} is removed".format(ETCD_DATA_DIR))
        except FileNotFoundError:
            pass

        def _set_etcd_file_owner(file_path):
            p = Path(file_path)
            p.parent.mkdir(parents=True, exist_ok=True)
            chown_cmd = "/usr/bin/chown -R dcos_etcd:dcos_etcd {}".format(
                file_path)
            run_command(chown_cmd)

        # Restoring will overwrite some snapshot metadata, like member ID and
        # cluster ID, to form a new cluster from the snapshot.
        # Here we initialize a standalone cluster, and new members will be
        # added to a cluster during dcos-etcd starting up by `join_cluster`
        # in `etcd_discovery.py`
        with tempfile.TemporaryDirectory(suffix="-restore-etcd") as tmp_dir:
            with tarfile.open(name=str(args.backup_path), mode='r:gz') as tar:
                tar.extractall(path=tmp_dir)
                snatshot_db_path = os.path.join(tmp_dir, self.SNAPSHOT_NAME)
                # the items in initial-advertise-peer-urls must be included in
                # initial-cluster items
                private_ip = detect_ip()
                master_ips = _get_master_ips()
                initial_cluster_items = [
                    "etcd-{}=https://{}:2380".format(master_ip, master_ip)
                    for master_ip in master_ips]
                initial_cluster = ",".join(initial_cluster_items)
                advertise_peer_urls = "https://{}:2380".format(private_ip)
                restore_cmd = (
                    "snapshot restore {} "
                    "--name etcd-{} "
                    "--data-dir {} "
                    "--initial-cluster {} "
                    "--initial-advertise-peer-urls {} "
                    "--initial-cluster-token etcd-dcos".format(
                        snatshot_db_path,
                        private_ip,
                        ETCD_DATA_DIR,
                        initial_cluster,
                        advertise_peer_urls,
                    ))
                self.execute_etcdctl(restore_cmd)

                _set_etcd_file_owner(ETCD_DATA_DIR)

                # initial state and cluster are required by etcd_discovery.py,
                # which expect an restored etcd behave the same as an normally
                # restarted one.
                Path(CLUSTER_NODES_PATH)
                with open(CLUSTER_NODES_PATH, "w") as f:
                    f.write(initial_cluster)
                _set_etcd_file_owner(CLUSTER_NODES_PATH)
                with open(CLUSTER_STATE_PATH, "w") as f:
                    f.write("new")
                _set_etcd_file_owner(CLUSTER_NODES_PATH)

        print('Local etcd instance restored successfully')


class EtcdDiagnostic(EtcdCmdBase):
    """Returns the status of etcd cluster and local node

    Diagnostic command prints health status of both the current instance and
    the cluster-wide with local instance as the endpoint.
    This command is recommended to be executed on every node running etcd in
    the quorum.
    """

    def __init__(self) -> None:
        super(EtcdDiagnostic, self).__init__()
        self.supported_cmd = ["diagnostic"]
        self.check_cmd_list = self.check_commands()

    @classmethod
    def check_commands(cls) -> list:
        # check the status of the current etcd instance
        endpoint_check_cmd = "endpoint health"
        # local endpoint is used for returning the etcd members, this is useful
        # to detect the split-brain of a cluster
        member_list_cmd = "member list -w json"

        return [endpoint_check_cmd, member_list_cmd]

    def diagnostic(self) -> None:
        for cmd in self.check_cmd_list:
            self.execute_etcdctl(cmd, user_master_endpoint=False)


class DCOSEtcdCli():

    def __init__(self) -> None:
        self.cmd_func_map = {}

    def register_cmd(self, cmd_object: EtcdCmdBase):
        for supported_cmd in cmd_object.supported_cmd:
            self.cmd_func_map[supported_cmd] = getattr(cmd_object,
                                                       supported_cmd)

    def execute(self):
        parser = argparse.ArgumentParser()
        parser.add_argument(
            'command',
            type=str,
            choices=self.cmd_func_map.keys(),
            help='CLI commands available',
        )
        args = parser.parse_args(sys.argv[1:2])
        self.cmd_func_map[args.command]()


if __name__ == '__main__':
    try:
        etcd_cli = DCOSEtcdCli()
        etcd_cli.register_cmd(EtcdBackupAndRestore())
        etcd_cli.register_cmd(EtcdDiagnostic())
        etcd_cli.execute()
    except subprocess.CalledProcessError as exc:
        if exc.output:
            sys.stdout.write(exc.output)
        sys.exit(exc.returncode)
