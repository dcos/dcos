# How to run the integration tests
```bash
pip3 install virtualenv
virtualenv venv
. venv/bin/activate
pip3 install -r requirements.txt
cd extra
pytest --env-help
pytest
```
