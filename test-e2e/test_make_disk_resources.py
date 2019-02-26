import json
import logging
from pathlib import Path

from _pytest.fixtures import SubRequest
from cluster_helpers import wait_for_dcos_oss
from dcos_e2e.backends import Docker
from dcos_e2e.cluster import Cluster
from dcos_e2e.node import Output
from dcos_test_utils.dcos_api import DcosApiSession, DcosUser
from dcos_test_utils.helpers import CI_CREDENTIALS
from docker.types import Mount
from py.path import local  # pylint: disable=no-name-in-module, import-error


def extract_mounts(mesos_resources: str) -> dict:
    """
    Read the Mesos resources file and return the mount volume (name + disk space).
    The file is not standard JSON thus parsing it is a cumbersome process.
    """
    cache_mounts = {}
    for line in str(mesos_resources).splitlines():
        if line.startswith('MESOS_RESOURCES'):
            data = json.loads(line[len('MESOS_RESOURCES=\''):-1])
            for item in data:
                if item["name"] == "disk" and "disk" in item and "source" in item["disk"]:
                    mount_volume = item["disk"]["source"]["mount"]["root"]
                    cache_mounts[mount_volume] = item["scalar"]["value"]
    return cache_mounts


class TestMakeDiskResources:
    """
    Tests for functionality specific to the make_disk_resources.py script.
    """
    def test_make_disk_resources(
        self,
        artifact_path: Path,
        tmpdir: local,
        request: SubRequest,
        log_dir: Path,
    ) -> None:
        """
        We check that make_disk_resources creates a mesos resources file with the
        previously available amount of space of the mount volume after the restart
        of an agent. If this was not the case and a task used one of the mount
        volumes, the Mesos agent process would refuse to restart as we can see in
        https://jira.mesosphere.com/browse/COPS-3527
        """
        custom_agent_mount = Mount(
            source=str(tmpdir.mkdir("mount")),
            target=str("/dcos/volume1"),
            type='bind',
        )

        mount_and_write_app = {
            "id": "/mount-test",
            "instances": 1,
            "cpus": 0.1,
            "mem": 128,
            "cmd": "head -c1000k </dev/urandom >$MESOS_SANDBOX/volume1/a.txt && sleep 1000",
            "container": {
                "type": "DOCKER",
                "volumes": [{
                    "persistent": {
                        "size": 10,
                        "type": "mount",
                        "constraints": [["path", "LIKE", "/dcos/volume1"]]
                    },
                    "mode": "RW",
                    "containerPath": "volume1"
                }],
                "docker": {
                    "image": "alpine",
                    "privileged": False,
                    "forcePullImage": False
                }
            },
            "upgradeStrategy": {
                "minimumHealthCapacity": 0.5,
                "maximumOverCapacity": 0
            },
            "unreachableStrategy": "disabled"
        }

        deploy_kwargs = {
            'check_health': False,
            'ignore_failed_tasks': True,
            'timeout': 600
        }

        backend = Docker(custom_agent_mounts=[custom_agent_mount])

        with Cluster(masters=1, agents=1, public_agents=0, cluster_backend=backend) as cluster:

            cluster.install_dcos_from_path(
                dcos_installer=artifact_path,
                dcos_config={
                    **cluster.base_config
                },
                ip_detect_path=backend.ip_detect_path,
            )

            # Wait for DC/OS to be ready for testing.
            wait_for_dcos_oss(
                cluster=cluster,
                request=request,
                log_dir=log_dir,
            )

            # albert@bekstil.net is test user recognized by dcos-test-utils library.
            create_user_args = ['.', '/opt/mesosphere/environment.export', '&&',
                                'python /opt/mesosphere/active/dcos-oauth/bin/dcos_add_user.py albert@bekstil.net']

            any_master = next(iter(cluster.masters))

            any_master.run(
                args=create_user_args,
                shell=True,
                output=Output.CAPTURE,
            )

            auth_user = DcosUser(CI_CREDENTIALS)

            scheme = 'http://'

            dcos_url = scheme + str(any_master.public_ip_address)

            dcos_api_session = DcosApiSession(
                dcos_url=dcos_url,
                masters=[str(n.public_ip_address) for n in cluster.masters],
                slaves=[str(n.public_ip_address) for n in cluster.agents],
                public_slaves=[
                    str(n.public_ip_address) for n in cluster.public_agents
                ],
                auth_user=auth_user
            )

            # Quirks of dcos-test-utils. This is required to get a authenticated user.
            dcos_api_session = dcos_api_session.get_user_session(auth_user)

            with dcos_api_session.marathon.deploy_and_cleanup(mount_and_write_app, **deploy_kwargs):
                logging.info('Successfully created task using mount volume')
                (agent, ) = cluster.agents

                cat_initial_mesos_resources = agent.run(args=['cat', '/var/lib/dcos/mesos-resources'])
                initial_mesos_resources = cat_initial_mesos_resources.stdout.decode("utf-8")
                initial_mount_volumes = extract_mounts(initial_mesos_resources)
                assert initial_mount_volumes != {}

                # Stop the Mesos agent process.
                agent.run(args=['systemctl', 'stop', 'dcos-mesos-slave'])
                # Move the mesos-resources to the cache as recommended in the docs.
                # We were previously simply deleting the file but we can now use it as a cache.
                agent.run(args=['mv', '-f', '/var/lib/dcos/mesos-resources', '/var/lib/dcos/mesos-resources.cache'])
                # Remove the agent checkpoint state as recommended in the docs.
                agent.run(args=['rm', '-f', '/var/lib/mesos/slave/meta/slaves/latest'])
                # Restart the Mesos agent process.
                agent.run(args=['systemctl', 'start', 'dcos-mesos-slave'])

                cat_new_mesos_resources = agent.run(args=['cat', '/var/lib/dcos/mesos-resources'])
                new_mesos_resources = cat_new_mesos_resources.stdout.decode("utf-8")
                new_mount_volumes = extract_mounts(new_mesos_resources)
                assert new_mount_volumes != {}

                # If make_disk_resources.py worked as expected, the mount
                # volumes will be the same even if the mount volume has
                # been used by mount_and_write_app.
                assert new_mount_volumes == initial_mount_volumes
