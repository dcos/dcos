# How to run the integration tests
```bash
pip install virtualenv
virtualenv venv
. venv/bin/activate
pip install -r requirements.txt
cd extra
pytest --env-help
pytest
```