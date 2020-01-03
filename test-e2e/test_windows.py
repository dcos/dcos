import os
import random
import re
import string
import subprocess
import sys
from pathlib import Path

import pytest
import requests
from _pytest.fixtures import SubRequest
from cluster_helpers import (
    wait_for_dcos_oss,
)
from dcos_e2e.backends import Docker
from dcos_e2e.cluster import Cluster
from dcos_e2e.node import Output


@pytest.fixture(scope='module')
def workspace_dir() -> Path:
    """
    Creates a known workspace directory.
    """
    tmp_dir_path = Path(os.environ['DCOS_E2E_TMP_DIR_PATH'])
    assert tmp_dir_path.exists() and tmp_dir_path.is_dir()

    subpath = ''.join(random.choice(string.ascii_lowercase) for i in range(5))

    return tmp_dir_path / subpath


def test_windows_agents(
    workspace_dir: Path,
    artifact_path: Path,
    request: SubRequest,
    log_dir: Path,
) -> None:
    """
    Enabling Windows agents creates additional configuration package
    and does not break Linux installation.
    """
    docker_backend = Docker(workspace_dir=workspace_dir)

    config = {
        'enable_windows_agents': True,
    }
    with Cluster(
        cluster_backend=docker_backend,
        agents=0,
        public_agents=0,
    ) as cluster:
        cluster.install_dcos_from_path(
            dcos_installer=artifact_path,
            dcos_config={
                **cluster.base_config,
                **config,
            },
            output=Output.LOG_AND_CAPTURE,
            ip_detect_path=docker_backend.ip_detect_path,
        )

        # Check that dcos-config-win.tar.xz was created
        paths = []
        for root, _, files in os.walk(str(workspace_dir)):
            for file in files:
                if file.startswith('dcos-config-win--setup_'):
                    paths.append(Path(root) / file)
        assert len(paths) == 1

        wait_for_dcos_oss(
            cluster=cluster,
            request=request,
            log_dir=log_dir,
        )


def _download_file(url: str, path: Path) -> None:
    with requests.get(url, stream=True) as r:
        r.raise_for_status()
        with path.open('wb') as f:
            for chunk in r.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)


def test_windows_install(
    tmp_path: Path,
) -> None:
    terraform_url = 'https://github.com/fatz/terraform/releases/download/v0.11.14-mesosphere/linux_amd64.zip'
    terraform_zip = tmp_path / 'terraform.zip'
    _download_file(terraform_url, terraform_zip)

    subprocess.run(('unzip', str(terraform_zip)), cwd=str(tmp_path), check=True)

    terraform = tmp_path / 'terraform'

    assert terraform.exists()

    terraform_zip.unlink()

    maintf_url = (
        'https://raw.githubusercontent.com/sergiimatusEPAM/examples/feature/'
        'windows-beta-support/aws/windows-agent/main.tf'
    )
    main_template = tmp_path / 'main.tf.in'
    _download_file(maintf_url, main_template)

    ssh_key = tmp_path / 'ssh'
    ssh_cert = ssh_key.with_suffix('.pub')
    subprocess.run(
        (
            'ssh-keygen',
            '-t', 'rsa',         # RSA key only
            '-f', str(ssh_key),  # filename of key file
            '-N', ''             # empty passphrase
        ),
        check=True
    )

    license_txt = tmp_path / 'license.txt'
    license_txt.write_text(os.environ['DCOS_LICENSE'])

    subs = (
        (re.compile(r'( *cluster_name *= *").*"'), r'\1test_windows_install"'),
        (re.compile(r'( *owner *= *").*"'), r'\1test-e2e"'),
        (
            re.compile(r'( *ssh_public_key_file *= *").*"'),
            r'\1' + str(ssh_cert).replace('\\', '\\\\') + '"'
        ),
        (
            re.compile(r'( *dcos_license_key_contents = ").*"$'),
            r'\1${file("' + str(license_txt).replace('\\', '\\\\') + '")}"'
        ),
    )

    creds_env = os.environ.copy()
    creds_env['AWS_ACCESS_KEY_ID'] = os.environ['AWS_PROD_ACCESS_KEY_ID']
    creds_env['AWS_SECRET_ACCESS_KEY'] = os.environ['AWS_PROD_SECRET_ACCESS_KEY']

    lineno = 1

    main_tf = tmp_path / 'main.tf'
    with main_template.open() as src:
        with main_tf.open('w') as dst:
            for line in src:
                for pat, repl in subs:
                    line = pat.sub(repl, line)
                sys.stderr.write('%d\t%s' % (lineno, line))
                lineno += 1
                dst.write(line)

    subprocess.run((str(terraform), 'init'), cwd=str(tmp_path), check=True)

    try:
        subprocess.run(
            (str(terraform), 'apply', '-auto-approve'),
            cwd=str(tmp_path), env=creds_env, check=True
        )
    finally:
        subprocess.run(
            (str(terraform), 'destroy', '-auto-approve'),
            cwd=str(tmp_path), env=creds_env, check=True
        )
