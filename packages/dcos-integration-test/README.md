# Preparation

Before the integration tests are run a virtual environment should be provisioned.

```bash
pip3 install virtualenv
virtualenv venv
. venv/bin/activate
pip3 install -r requirements.txt
```

You can verify it with
```
cd extra
pytest --env-help
```

If you have [pyenv](https://github.com/pyenv/pyenv) with [pyenv-virtualenv](https://github.com/pyenv/pyenv-virtualenv)
installed you can run

```bash
pyenv virtualenv 3.6.3 dcos_env
pyenv activate dcos_env
pip install -r requirements.txt
```

# Running the Tests

This assumes that a cluster is running. Note: If you use an DC/OS Open cluster you must not setup the CLI nor login.
The ACS token is valid only once.

Run the simple test with

```bash
export DCOS_ACS_TOKEN="$(dcos config show core.dcos_acs_token)"
export DCOS_SSH_USE=centos
pytest -v -x --capture=no --full-trace --log-level=DEBUG test_applications.py::test_if_marathon_app_can_be_deployed
```

Alternatively you should be able to run `terraform_test.sh` in case you provisioned the cluster with Terraform.

The Windows tests are run by passing `--windows-only`.
