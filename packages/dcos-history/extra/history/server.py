import logging
import os

import history.server_util

app = history.server_util.create_app()


def start():
    logging.warning("This service is deprecated and will be removed in a future version of DC/OS")
    os.system("gunicorn --bind 0.0.0.0:15055 server:app")
