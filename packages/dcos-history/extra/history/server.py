import os
import history.server_util

app = history.server_util.create_app()


def start():
    os.system("gunicorn --bind 0.0.0.0:15055 server:app")
