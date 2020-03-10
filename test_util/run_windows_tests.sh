    cd ../packages/dcos-integration-test
    pip3 install virtualenv
    virtualenv venv
    . venv/bin/activate
    pip3 install -r requirements.txt	
    cd extra
    export DCOS_ACS_TOKEN="$(dcos config show core.dcos_acs_token)"
    export DCOS_SSH_USE=centos
    pytest -v -x --capture=no --full-trace --log-level=DEBUG --windows-only
