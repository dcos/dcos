"""
Tests for calico network containers Different from tests under
packages/dcos-integration-test/test_calico_networking.py which tests only with
default parameters, current tests also take into consideration scenerios when
different configurations exposed to the operators are enabled.
"""
import uuid
from pathlib import Path

from _pytest.fixtures import SubRequest
from cluster_helpers import wait_for_dcos_oss
from dcos_e2e.backends import Docker
from dcos_e2e.cluster import Cluster
from dcos_e2e.node import Output
from passlib.hash import sha512_crypt


def test_calico_disabled(docker_backend: Docker, artifact_path: Path,
                         request: SubRequest, log_dir: Path) -> None:
    with Cluster(
            cluster_backend=docker_backend,
            masters=1,
            agents=1,
            public_agents=1,
    ) as cluster:
        config = {"calico_enabled": "false"}
        cluster.install_dcos_from_path(
            dcos_installer=artifact_path,
            dcos_config={
                **cluster.base_config,
                **config,
            },
            output=Output.LOG_AND_CAPTURE,
            ip_detect_path=docker_backend.ip_detect_path,
        )
        wait_for_dcos_oss(
            cluster=cluster,
            request=request,
            log_dir=log_dir,
        )
        for node in cluster.masters | cluster.agents | cluster.public_agents:
            result = node.run(
                args=["systemctl show dcos-calico-node"],
                output=Output.LOG_AND_CAPTURE,
                shell=True,
            )
            calico_node_properties = result.stdout.strip().decode()
            # dcos calico node should be inactive as a result of condition
            # check failure
            assert "ActiveState=inactive" in calico_node_properties
            assert "ConditionResult=no" in calico_node_properties


def test_calico_vxlan(docker_backend: Docker, artifact_path: Path,
                      request: SubRequest, log_dir: Path) -> None:
    with Cluster(
            cluster_backend=docker_backend,
            masters=1,
            agents=2,
            public_agents=1,
    ) as cluster:
        superuser_username = str(uuid.uuid4())
        superuser_password = str(uuid.uuid4())
        config = {
            "superuser_username": superuser_username,
            # We can hash the password with any `passlib`-based method here.
            # We choose `sha512_crypt` arbitrarily.
            "superuser_password_hash": sha512_crypt.hash(superuser_password),
            "calico_vxlan_enabled": "true",
            "calico_network_cidr": "192.168.128.0/17",
        }
        cluster.install_dcos_from_path(
            dcos_installer=artifact_path,
            dcos_config={
                **cluster.base_config,
                **config,
            },
            output=Output.LOG_AND_CAPTURE,
            ip_detect_path=docker_backend.ip_detect_path,
        )
        wait_for_dcos_oss(
            cluster=cluster,
            request=request,
            log_dir=log_dir,
        )

        environment_variables = {
            "DCOS_LOGIN_UNAME":
            superuser_username,
            "DCOS_LOGIN_PW":
            superuser_password,
            "MASTER_PUBLIC_IP":
            list(cluster.masters)[0].public_ip_address,
            "MASTERS_PRIVATE_IPS":
            [node.private_ip_address for node in cluster.masters],
            "PUBLIC_AGENTS_PRIVATE_IPS":
            [node.public_ip_address for node in cluster.public_agents],
            "PRIVATE_AGENTS_PRIVATE_IPS":
            [node.private_ip_address for node in cluster.agents],
        }
        pytest_command = [
            "pytest",
            "-vvv",
            "-s",
            "-x",
            "test_calico_networking.py",
        ]
        cluster.run_with_test_environment(
            args=pytest_command,
            env=environment_variables,
            output=Output.LOG_AND_CAPTURE,
        )
