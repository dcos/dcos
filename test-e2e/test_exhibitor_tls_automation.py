from contextlib import contextmanager
from pathlib import Path
from subprocess import CalledProcessError
from time import sleep
from typing import Iterable, Iterator

import pytest
from _pytest.fixtures import SubRequest
from cluster_helpers import (
    wait_for_dcos_oss,
)

from dcos_e2e.base_classes import ClusterBackend
from dcos_e2e.cluster import Cluster, Node
from dcos_e2e.node import Output


class TestExhibitorTLSAutomation:
    """
    Test automated Exhibitor TLS feature.
    """

    def test_exhibitor_tls_disabled(
        self,
        docker_backend: ClusterBackend,
        artifact_path: Path,
        request: SubRequest,
        log_dir: Path,
    ) -> None:
        """
        Test disabling Exhibitor TLS.
        """
        with Cluster(
            cluster_backend=docker_backend,
            masters=1,
            agents=0,
            public_agents=0,
        ) as cluster:
            cluster.install_dcos_from_path(
                dcos_installer=artifact_path,
                dcos_config={
                    **cluster.base_config,
                    **{'exhibitor_tls_enabled': 'false'},
                },
                output=Output.LOG_AND_CAPTURE,
                ip_detect_path=docker_backend.ip_detect_path,
            )
            wait_for_dcos_oss(
                cluster=cluster,
                request=request,
                log_dir=log_dir,
            )
            master = next(iter(cluster.masters))
            master.run(
                ['curl',
                 '-fsSL',
                 'http://$(/opt/mesosphere/bin/detect_ip):8181/exhibitor/v1/cluster/status'],
                output=Output.LOG_AND_CAPTURE,
                shell=True,
            )

    def test_exhibitor_tls_custom_ca_url(
        self,
        docker_backend: ClusterBackend,
        artifact_path: Path,
        request: SubRequest,
        log_dir: Path,
    ) -> None:
        """
        Test Exhibitor TLS with custom CSR service URL.
        """
        # TODO(tweidner):
        # Start initialized `dcoscertstrap` Docker container on host network.
        # $ ./dcoscertstrap init-ca --sans 172.17.0.1
        # $ ./dcoscertstrap serve
        # Point `exhibitor_bootstrap_ca_url` URL to it.
        with Cluster(
            cluster_backend=docker_backend,
            masters=1,
            agents=0,
            public_agents=0,
        ) as cluster:
            master = next(iter(cluster.masters))
            master.send_file(
                local_path=Path('/home/tim/Downloads/dcoscertstrap_0.0.2_linux_amd64/dcoscertstrap'),
                remote_path=Path('/dcoscertstrap'),
            )
            master.run(
                args=['/dcoscertstrap', 'init-ca', '--sans', 'localhost'],
                output=Output.LOG_AND_CAPTURE,
            )
            master.run(
                args=['/dcoscertstrap', 'serve', '--address', 'localhost:7019'],
                output=Output.LOG_AND_CAPTURE,
            )
            master.run(
                args=['cp', '/.dcos-pki/root-cert.pem', '/dcoscertstrap-root-cert.pem'],
                output=Output.LOG_AND_CAPTURE,
            )
            import pdb; pdb.set_trace()
            cluster.install_dcos_from_path(
                dcos_installer=artifact_path,
                dcos_config={
                    **cluster.base_config,
                    **{'exhibitor_bootstrap_ca_url': 'https://localhost:7019'},
                },
                output=Output.LOG_AND_CAPTURE,
                ip_detect_path=docker_backend.ip_detect_path,
            )
            wait_for_dcos_oss(
                cluster=cluster,
                request=request,
                log_dir=log_dir,
            )
            with pytest.raises(CalledProcessError) as exc:
                master.run(
                    ['curl',
                     '-fsSL',
                     'http://$(/opt/mesosphere/bin/detect_ip):8181/exhibitor/v1/cluster/status'],
                    output=Output.LOG_AND_CAPTURE,
                    shell=True,
                )
            assert exc.value.message == '<some cURL TLS error>'

    def test_exhibitor_existing_partial_tls_artifacts(
        self,
        docker_backend: ClusterBackend,
        artifact_path: Path,
        request: SubRequest,
        log_dir: Path,
    ) -> None:
        """
        Tests for `truststore` place.
        """
        with Cluster(
            cluster_backend=docker_backend,
            masters=1,
            agents=0,
            public_agents=0,
        ) as cluster:
            cluster.install_dcos_from_path(
                dcos_installer=artifact_path,
                dcos_config=cluster.base_config,
                output=Output.LOG_AND_CAPTURE,
                ip_detect_path=docker_backend.ip_detect_path,
            )
            wait_for_dcos_oss(
                cluster=cluster,
                request=request,
                log_dir=log_dir,
            )
            master = next(iter(cluster.masters))

            tls_artifacts_path = Path('/var/lib/dcos/exhibitor-tls-artifacts')
            truststore_path = Path(tls_artifacts_path / 'truststore.jks')
            serverstore_path = Path(tls_artifacts_path / 'serverstore.jks')
            clientstore_path = Path(tls_artifacts_path / 'clientstore.jks')

            dcos_exhibitor_service = 'dcos-exhibitor.service'
            master.run(args=['systemctl', 'stop', dcos_exhibitor_service])

            all_paths = set([truststore_path, serverstore_path, clientstore_path])

            for path in all_paths:
                master.run(args=['rm', '-f', str(path)])

            import itertools
            singles = set(itertools.combinations(iterable=all_paths, r=1))
            pairs = set(itertools.combinations(iterable=all_paths, r=2))
            incomplete_path_sets = singles.union(pairs)

            for path_set in incomplete_path_sets:

                with _temporary_remote_files(master, path_set):

                    missing_path_set = all_paths - set(path_set)

                    for tls_artifact in missing_path_set:
                        error_message = ('{} not found.'.format(tls_artifact))

                        seconds = 2
                        sleep(seconds)
                        assert error_message in _dumped_journal_after_run(
                            node=master,
                            unit=dcos_exhibitor_service,
                            seconds=seconds,
                        )


@contextmanager
def _temporary_remote_files(node: Node, paths: Iterable[Path]) -> Iterator[None]:
    """
    Create empty files temporarily on the remote node.
    """
    for path in paths:
        node.run(['touch', str(path)])
    try:
        yield
    finally:
        for path in paths:
            node.run(['rm', str(path)])


def _dumped_journal_after_run(node: Node, unit: str, seconds: int) -> str:
    node.run(['systemctl', 'start', unit])
    capture_logs_args = [
        'journalctl',
        '-u',
        unit,
        '--no-pager',
        "--since='{} seconds ago'".format(seconds),
    ]
    result = node.run(
        args=capture_logs_args,
        output=Output.LOG_AND_CAPTURE,
    )
    node.run(['systemctl', 'stop', unit])
    return str(result.stdout.decode())
