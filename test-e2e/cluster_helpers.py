"""
Helpers for working with DC/OS E2E clusters.
"""

import logging
from datetime import datetime
from pathlib import Path
from subprocess import CalledProcessError
from typing import List

from _pytest.fixtures import SubRequest

from dcos_e2e.cluster import Cluster
from dcos_e2e.exceptions import DCOSTimeoutError
from dcos_e2e.node import Node


LOGGER = logging.getLogger(__name__)


def wait_for_dcos_oss(
    cluster: Cluster,
    request: SubRequest,
    log_dir: Path,
) -> None:
    """
    Helper for ``wait_for_dcos_oss`` that automatically dumps the journal of
    every cluster node if a ``DCOSTimeoutError`` is hit.
    """
    try:
        cluster.wait_for_dcos_oss()
    except DCOSTimeoutError:
        # Dumping the logs on timeout only works if DC/OS has already started
        # the systemd units that the logs are retrieved from.
        # This does currently not pose a problem since the ``wait_for_dcos_ee``
        # timeout is set to one hour. We expect the systemd units to have
        # started by then.
        dump_cluster_journals(
            cluster=cluster,
            target_dir=log_dir / artifact_dir_format(request.node.name),
        )
        raise


def artifact_dir_format(test_name: str) -> str:
    """
    Create a common target test directory name format.
    """
    return test_name + '_' + str(datetime.now().isoformat().split('.')[0])


def dump_cluster_journals(cluster: Cluster, target_dir: Path) -> None:
    """
    Dump logs for each cluster node to the ``target_dir``. Logs are separated into directories per node.
    """
    target_dir.mkdir(parents=True)
    for role, nodes in (
        ('master', cluster.masters),
        ('agent', cluster.agents),
        ('public_agent', cluster.public_agents),
    ):
        for index, node in enumerate(nodes):
            node_str = (
                '{role}-{index}_{private_ip}'
            ).format(
                role=role,
                index=index,
                private_ip=node.private_ip_address,
            )
            node_dir = Path(target_dir) / node_str
            _dump_node_journals(node, node_dir)


def _dump_node_journals(node: Node, node_dir: Path) -> None:
    """
    Dump logs from the given cluster node to the ``node_dir``.

    Dumping the diagnostics bundle is unreliable in case that DC/OS
    components are broken. This is likely if ``wait_for_dcos_ee``
    times out. Instead this dumps the journal for each systemd unit
    started by DC/OS.
    """
    LOGGER.info('Dumping journals from {node}'.format(node=node))
    node_dir.mkdir(parents=True)
    try:
        _dump_stdout_to_file(node, ['journalctl'], node_dir / _log_filename('journal'))
    except CalledProcessError as exc:
        # Continue dumping further journals even if an error occurs.
        LOGGER.warn('Unable to dump journalctl: {exc}'.format(exc=str(exc)))

    for unit in _dcos_systemd_units(node):
        if unit.endswith('.service'):
            name = unit.split('.')[0]
            try:
                _dump_stdout_to_file(
                    node=node,
                    cmd=['journalctl', '-u', unit],
                    file_path=node_dir / _log_filename(name),
                )
            except CalledProcessError as exc:
                # Continue dumping further journals even if an error occurs.
                message = 'Unable to dump {unit} journal: {exc}'.format(
                    unit=unit,
                    exc=str(exc),
                )
                LOGGER.warn(message)


def _dump_stdout_to_file(node: Node, cmd: List[str], file_path: Path) -> None:
    """
    Dump ``stdout`` of the given command to ``file_path``.

    Raises:
        CalledProcessError: If an error occurs when running the given command.
    """
    chunk_size = 2048
    proc = node.popen(args=cmd)
    with open(str(file_path), 'wb') as dumpfile:
        while True:
            chunk = proc.stdout.read(chunk_size)
            if chunk:
                dumpfile.write(chunk)
            else:
                break
    proc.wait()
    if proc.returncode != 0:
        exception = CalledProcessError(
            returncode=proc.returncode,
            cmd=cmd,
            output=bytes(proc.stdout),
            stderr=bytes(proc.stderr),
        )
        message = (
            'Failed to complete "{cmd}": {exception}'
        ).format(
            cmd=cmd,
            exception=exception,
        )
        LOGGER.warn(message)
        raise exception


def _dcos_systemd_units(node: Node) -> List[str]:
    """
    Return all systemd services that are started up by DC/OS.
    """
    result = node.run(
        args=[
            'sudo', 'systemctl', 'show', '-p', 'Wants', 'dcos.target', '|',
            'cut', '-d=', '-f2'
        ],
        shell=True,
    )
    systemd_units_string = result.stdout.strip().decode()
    return str(systemd_units_string).split(' ')


def _log_filename(name: str) -> Path:
    """
    Returns a name of the file with `.log` extension.
    """
    return Path(name).with_suffix('.log')
