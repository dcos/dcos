"""
need to fix error from mkfs
"""
import os
import re
import stat
import tempfile

import pytest

from ssh.ssh_tunnel import SSHTunnel

MOUNT_PATTERN = re.compile(
    'on\s+(/dcos/volume([^0][0-9]{2,}|[0]\d{3,}))\s+', re.M | re.I
)


def sudo(cmd):
    return ['sudo'] + cmd


def mesos_agent(cmd):
    return sudo(['systemctl', cmd, 'dcos-mesos-slave'])


def volume_discovery(cmd):
    return sudo(['systemctl', cmd, 'dcos-vol-discovery-priv-agent'])


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
def resetting_agent(agent_tunnel):
    roles = agent_tunnel.remote_cmd(['ls', '/etc/mesosphere/roles']).decode()
    if 'slave' not in roles:
        pytest.skip('Test must be run on an agent!')
    yield agent_tunnel
    agent_tunnel.remote_cmd(mesos_agent('stop'))
    # Cleanup in case removing volumes previously failed
    # mount_blob = agent_tunnel.remove_cmd(['mount']).decode()
    # dcos_mounts = MOUNT_PATTERN.findall(mount_blob)
    # cmds = [sudo(['/usr/bin/umount', m[0]]) for m in dcos_mounts]
    # for cmd in cmds:
    #     agent_tunnel.remote_cmd(cmd)
    agent_tunnel.remote_cmd(clear_volume_discovery_state())
    agent_tunnel.remote_cmd(volume_discovery('start'))
    agent_tunnel.remote_cmd(clear_mesos_agent_state())
    agent_tunnel.remote_cmd(mesos_agent('start'))


class VolumeManager:

    def __init__(self, tunnel):
        self.tunnel = tunnel
        self.volumes = []

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
            self.tunnel.remote_cmd(
                sudo(['dd', 'of='+img, 'if=/dev/null', 'bs=1M', 'count='+str(vol_size)]))
            loop_device = self.tunnel.remote_cmd(['losetup', '--find']).decode().strip('\n')
            cmds = (
                ['/usr/bin/mkdir', '-p', mount_point],
                ['/usr/sbin/losetup', loop_device, img],
                ['/usr/sbin/mkfs', '-t', 'ext4', loop_device],
                ['/usr/bin/mount', loop_device, mount_point])
            for cmd in cmds:
                self.tunnel.remote_cmd(sudo(cmd))
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
    agent_tunnel.remote_cmd(volume_discovery('start'))
    agent_tunnel.remote_cmd(mesos_agent('start'))
    # assert on mounted resources
    for d in get_state_json(cluster):
        for size, _, vol in volume_manager.volumes:
            assert vol not in d


def test_missing_disk_resource_file(agent_tunnel):
    agent_tunnel.remote_cmd(mesos_agent('stop'))
    agent_tunnel.remote_cmd(clear_volume_discovery_state())
    started = agent_tunnel.remote_cmd(mesos_agent('start')).decode()
    assert 'error' in started.lower()


def test_add_volume_works(agent_tunnel, volume_manager, cluster):
    agent_tunnel.remote_cmd(mesos_agent('stop'))
    volume_manager.add_volumes_to_agent((200, 200))
    clear_volume_discovery_state()
    agent_tunnel.remote_cmd(clear_volume_discovery_state())
    agent_tunnel.remote_cmd(clear_mesos_agent_state())
    agent_tunnel.remote_cmd(mesos_agent('start'))
    # assert on mounted resources
    for d in get_state_json(cluster):
        for _, _, vol in volume_manager.volumes:
            assert vol in d


def test_vol_discovery_fails_due_to_size(agent_tunnel, volume_manager):
    agent_tunnel.remote_cmd(mesos_agent('stop'))
    volume_manager.add_volumes_to_agent((200, 200, 50,))
    agent_tunnel.remote_cmd(volume_discovery('start'))
    res_file = agent_tunnel.remote_cmd(['ls', '/var/lib/dcos/mesos-resources']).decode()
    assert 'No such file or directory' in res_file


def test_vol_discovery_non_json_mesos_resources(agent_tunnel):
    write_bad_file = ['printf', 'MESOS_RESOURCES=ports:[1025-2180]', '>', '/etc/mesos-slave']
    agent_tunnel.remote_cmd(sudo(write_bad_file))
    discovery_status = agent_tunnel.remote_cmd(volume_discovery('start'))
    assert 'error' in discovery_status
