"""
Test for mesos agent volume mounting capabilities
Note: This only supports onprem installations. Specifically, persistent nodes are required.
If run against an AWS stack with autoscaling groups, the instances
will be reprovisioned once the health checks are failed
TODO: add tests that very that a unhealthy state is made on certain mount conditions
"""
import os
import stat
import tempfile
import time

import pytest
import retrying

from ssh.ssh_tunnel import SSHTunnel
from test_util.aws import BotoWrapper

ENV_FLAG = 'ENABLE_VOLUME_TESTING'

pytestmark = pytest.mark.skipif(
    ENV_FLAG not in os.environ or os.environ[ENV_FLAG] != 'true',
    reason='Must explicitly enable volume testing with {}'.format(ENV_FLAG))

add_vol_script = """#!/bin/bash
mkdir -p $1
dd if=/dev/zero of=$2 bs=1M count=$3
free_loop=`losetup --find`
losetup $free_loop $2
mkfs -t ext4 $free_loop
losetup -d $free_loop
echo "$2 $1 auto loop 0 2" | tee -a /etc/fstab
mount $1
"""


def sudo(cmd):
    return ['sudo'] + cmd


def reboot_agent(private_ip_address):
    bw = BotoWrapper(os.environ['AWS_REGION'], os.environ['AWS_ACCESS_KEY_ID'], os.environ['AWS_SECRET_ACCESS_KEY'])
    reservations = bw.client('ec2').describe_instances(Filters=[
        {'Name': 'tag-value', 'Values': [os.environ['AWS_STACK_NAME']]},
        {'Name': 'private-ip-address', 'Values': [private_ip_address]}])['Reservations']
    for r in reservations:
        for i in r['Instances']:
            if i['State']['Name'] == 'running':
                bw.resource('ec2').Instance(i['InstanceId']).reboot()
                # reboot is an asynchronous call, so add some buffer here
                time.sleep(15)
                return


def mesos_agent(cmd):
    return sudo(['systemctl', cmd, 'dcos-mesos-slave'])


def clear_mesos_agent_state():
    return sudo(['rm', '-rf', '/var/lib/mesos/slave'])


def clear_volume_discovery_state():
    return sudo(['rm', '/var/lib/dcos/mesos-resources'])


@retrying.retry(wait_fixed=3000, stop_max_delay=300 * 1000)
def wait_for_ssh_tunnel(tunnel):
    SSHTunnel(tunnel.ssh_user, tunnel.ssh_key_path, tunnel.host)
    # check that original tunnel still works
    tunnel.remote_cmd(['pwd'])


@pytest.yield_fixture(scope='function')
def agent_tunnel(cluster):
    """ Opens an SSHTunnel with and clean up SSH key afterwards
    """
    ssh_key = os.environ['DCOS_SSH_KEY']
    ssh_user = os.environ['DCOS_SSH_USER']
    host = cluster.slaves[0]
    with tempfile.NamedTemporaryFile(delete=False) as f:
        f.write(ssh_key.encode())
        ssh_key_path = f.name
    os.chmod(ssh_key_path, stat.S_IREAD | stat.S_IWRITE)
    yield SSHTunnel(ssh_user, ssh_key_path, host)
    os.remove(ssh_key_path)


@pytest.yield_fixture(scope='function')
def resetting_agent(agent_tunnel, cluster):
    roles = agent_tunnel.remote_cmd(['ls', '/etc/mesosphere/roles']).decode()
    if 'slave' not in roles:
        pytest.skip('Test must be run on an agent!')
    yield agent_tunnel
    agent_tunnel.remote_cmd(mesos_agent('stop'))
    agent_tunnel.remote_cmd(clear_volume_discovery_state())
    agent_tunnel.remote_cmd(clear_mesos_agent_state())
    reboot_agent(agent_tunnel.host)
    wait_for_ssh_tunnel(agent_tunnel)
    cluster.wait_for_dcos()


class VolumeManager:

    def __init__(self, tunnel):
        self.tunnel = tunnel
        self.volumes = []
        self.tmp_path
        with tempfile.NamedTemporaryFile(delete=False) as f:
            f.write(add_vol_script.encode())
            self.tmp_path = f.name
        self.tunnel.write_to_remote(self.tmp_path, '/tmp/add_vol.sh')

    def purge_volumes(self):
        for i, vol in enumerate(self.volumes):
            cmds = (
                ['/usr/bin/umount', vol[2]],
                ['rm', '-f', vol[1]])
            for cmd in cmds:
                self.tunnel.remote_cmd(sudo(cmd))
        self.volumes = []

    def add_volumes_to_agent(self, vol_sizes):
        # reserve /dcos/volume100+ for our tests
        for i, vol_size in enumerate(vol_sizes, 100):
            img = '/root/{}.img'.format(i)
            mount_point = '/dcos/volume{}'.format(i)
            self.tunnel.remote_cmd(sudo(['bash', '/tmp/vol_add.sh', mount_point, img, str(vol_size)]))
            self.volumes.append((vol_size, img, mount_point))


def get_state_json(cluster):
    r = cluster.get('/mesos/master/slaves')
    data = r.json()
    slaves_ids = sorted(x['id'] for x in data['slaves'])

    for slave_id in slaves_ids:
        uri = '/slave/{}/slave%281%29/state.json'.format(slave_id)
        r = cluster.get(uri)
        assert r.ok
        data = r.json()
        yield data


@pytest.yield_fixture(scope='function')
def volume_manager(resetting_agent):
    volume_mgr = VolumeManager(resetting_agent)
    yield volume_mgr
    volume_mgr.purge_volumes()
    os.remove(volume_mgr.tmp_path)


def test_add_volume_noop(agent_tunnel, volume_manager, cluster):
    agent_tunnel.remote_cmd(mesos_agent('stop'))
    volume_manager.add_volumes_to_agent((200, 200))
    reboot_agent(agent_tunnel.host)
    wait_for_ssh_tunnel(agent_tunnel)
    cluster.wait_for_dcos()
    # assert on mounted resources
    for d in get_state_json(cluster):
        for size, _, vol in volume_manager.volumes:
            assert vol not in d


def test_add_volume_works(agent_tunnel, volume_manager, cluster):
    agent_tunnel.remote_cmd(mesos_agent('stop'))
    agent_tunnel.remote_cmd(clear_volume_discovery_state())
    agent_tunnel.remote_cmd(clear_mesos_agent_state())
    volume_manager.add_volumes_to_agent((200, 200))
    reboot_agent(agent_tunnel.host)
    wait_for_ssh_tunnel(agent_tunnel)
    cluster.wait_for_dcos()
    # assert on mounted resources
    for d in get_state_json(cluster):
        for _, _, vol in volume_manager.volumes:
            assert vol in d
