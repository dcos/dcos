"""
need to fix error from mkfs
"""
import os
import stat
import tempfile

import pytest

from ssh.ssh_tunnel import SSHTunnel

ENV_FLAG = 'ENABLE_RESILIENCY_TESTING'

pytestmark = pytest.mark.skipif(
    ENV_FLAG not in os.environ or os.environ[ENV_FLAG] != 'true',
    reason='Must explicitly enable resiliency testing with {}'.format(ENV_FLAG))

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


def mesos_agent(cmd):
    return sudo(['systemctl', cmd, 'dcos-mesos-slave'])


def clear_mesos_agent_state():
    return sudo(['rm', '-rf', '/var/lib/mesos/slave'])


def clear_volume_discovery_state():
    return sudo(['rm', '/var/lib/dcos/mesos-resources'])


@pytest.yield_fixture(scope='session')
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
    agent_tunnel.remote_cmd(mesos_agent('start'))
    cluster.wait_for_up()


class VolumeManager:

    def __init__(self, tunnel):
        self.tunnel = tunnel
        self.volumes = []
        self.script_path

    def __enter__(self):
        with tempfile.NamedTemporaryFile() as f:
            f.write(add_vol_script.encode())
            self.tunnel.write_to_remote(f.name, '/tmp/add_vol.sh')

    def purge_volumes(self):
        for i, _, img, vol in enumerate(self.volumes[:]):
            cmds = (
                ['/usr/bin/umount', vol],
                ['/usr/sbin/losetup', '--detach', vol],
                ['rm', '-f', img])
            for cmd in cmds:
                self.tunnel.remote_cmd(sudo(cmd))
            del self.volumes[i]

    def add_volumes_to_agent(self, vol_sizes):
        # reserve /dcos/volume100+ for our tests
        for i, vol_size in enumerate(vol_sizes, 100):
            img = '/root/{}.img'.format(i)
            mount_point = '/dcos/volume{}'.format(i)
            self.tunnel.remote_cmd(sudo(['bash', '/home/core/vol_add.sh', mount_point, img, str(vol_size)]))
            self.volumes.append((vol_size, img, mount_point))


def get_state_json(cluster):
    r = cluster.get('/mesos/master/slaves')
    data = r.json()
    slaves_ids = sorted(x['id'] for x in data['slaves'])

    for slave_id in slaves_ids:
        uri = '/slave/{}/slave%281%29/state.json'.format(slave_id)
        r = cluster.get(uri)
        data = r.json()
        yield data


@pytest.yield_fixture(scope='function')
def volume_manager(resetting_agent):
    volume_mgr = VolumeManager(resetting_agent)
    yield volume_mgr
    volume_mgr.purge_volumes()


def test_add_volume_noop(agent_tunnel, volume_manager, cluster):
    agent_tunnel.remote_cmd(mesos_agent('stop'))
    volume_manager.add_volumes_to_agent((200, 200))
    agent_tunnel.remote_cmd(mesos_agent('start'))
    # assert on mounted resources
    for d in get_state_json(cluster):
        for size, _, vol in volume_manager.volumes:
            assert vol not in d


def Dtest_missing_disk_resource_file(agent_tunnel):
    agent_tunnel.remote_cmd(mesos_agent('stop'))
    agent_tunnel.remote_cmd(clear_volume_discovery_state())
    started = agent_tunnel.remote_cmd(mesos_agent('start')).decode()
    assert 'error' in started.lower()


def Dtest_add_volume_works(agent_tunnel, volume_manager, cluster):
    agent_tunnel.remote_cmd(mesos_agent('stop'))
    agent_tunnel.remote_cmd(clear_volume_discovery_state())
    agent_tunnel.remote_cmd(clear_mesos_agent_state())
    volume_manager.add_volumes_to_agent((200, 200))
    agent_tunnel.remote_cmd(sudo('reboot'))
    cluster.wait_for_up()
    # assert on mounted resources
    for d in get_state_json(cluster):
        for _, _, vol in volume_manager.volumes:
            assert vol in d


def Dtest_vol_discovery_fails_due_to_size(agent_tunnel, volume_manager):
    agent_tunnel.remote_cmd(mesos_agent('stop'))
    volume_manager.add_volumes_to_agent((200, 200, 50,))
    agent_tunnel.remote_cmd(mesos_agent('start'))
    res_file = agent_tunnel.remote_cmd(['ls', '/var/lib/dcos/mesos-resources']).decode()
    assert 'No such file or directory' in res_file


def Dtest_vol_discovery_non_json_mesos_resources(agent_tunnel):
    agent_tunnel.remote_cmd(mesos_agent('stop'))
    write_bad_file = ['printf', 'MESOS_RESOURCES=ports:[1025-2180]', '>', '/etc/mesos-slave']
    agent_tunnel.remote_cmd(sudo(write_bad_file))
    discovery_status = agent_tunnel.remote_cmd(mesos_agent('start'))
    assert 'error' in discovery_status
