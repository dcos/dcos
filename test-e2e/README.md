This directory contains end to end tests.

To run these tests, create an environment which can run DC/OS E2E with Docker nodes as per the [requirements documentation](https://dcos-e2e.readthedocs.io/en/latest/docker-backend.html#requirements).

Then, download the relevant build artifact and set various environment variables.
For example:

```sh
ARTIFACT_URL=https://downloads.dcos.io/dcos/testing/master/dcos_generate_config.sh
export DCOS_E2E_GENCONF_PATH=/tmp/dcos_generate_config.sh
export DCOS_E2E_TMP_DIR_PATH=/tmp
export DCOS_E2E_LOG_DIR=/tmp/logs

rm -rf $DCOS_E2E_GENCONF_PATH
curl -o $DCOS_E2E_GENCONF_PATH $ARTIFACT_URL
```

Then, install the test dependencies, preferably in a virtual environment:

```sh
pip3 install -r requirements.txt
```

and run the tests:

```sh
pytest --confcutdir .
```
