import logging
import os
import sys


from flask import Flask, Response
from flask.ext.compress import Compress
from history.statebuffer import BufferCollection, BufferUpdater


app = Flask(__name__)
compress = Compress()
state_buffer = None
log = logging.getLogger(__name__)
add_headers_cb = None


try:
    import dcos_auth_python
    log.info('dcos_auth_python module detected; applying settings')
    global add_headers_cb
    add_headers_cb = dcos_auth_python.get_auth_headers
except ImportError:
    log.info('no dcos_auth_python module detected; using defaults')


def headers_cb():
    """Callback method for providing headers per request

    add_headers_cb is another callback providing headers (as a dict) to update the
    defaults in this method. This method can be set by adding a dcos_auth_python package
    with a get_auth_headers method
    """
    headers = {
        "Access-Control-Allow-Credentials": "true",
        "Access-Control-Allow-Headers": "accept, accept-charset, accept-encoding, " +
                                        "accept-language, authorization, content-length, " +
                                        "content-type, host, origin, proxy-connection, " +
                                        "referer, user-agent, x-requested-with",
        "Access-Control-Allow-Methods": "HEAD, GET, PUT, POST, PATCH, DELETE",
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Max-Age": "86400"}
    if add_headers_cb:
        headers.update(add_headers_cb())
    return headers


@app.route('/')
def home():
    return _response_("history/last - to get the last fetched state\n" +
                      "history/minute - to get the state array of the last minute\n" +
                      "history/hour - to get the state array of the last hour\n" +
                      "ping - to get a pong\n")


@app.route('/ping')
def ping():
    return _response_("pong")


@app.route('/history/last')
def last():
    return _response_(state_buffer.dump('last')[0])


@app.route('/history/minute')
def minute():
    return _buffer_response_('minute')


@app.route('/history/hour')
def hour():
    return _buffer_response_('hour')


def _buffer_response_(name):
    return _response_("[" + ",".join(state_buffer.dump(name)) + "]")


def _response_(content):
    return Response(response=content, content_type="application/json", headers=headers_cb())


def on_starting_server(server):
    global state_buffer
    logging.basicConfig(format='[%(levelname)s:%(asctime)s] %(message)s', level='INFO')

    compress.init_app(app)

    if 'HISTORY_BUFFER_DIR' not in os.environ:
        sys.exit('HISTORY_BUFFER_DIR must be set!')

    state_buffer = BufferCollection(os.environ['HISTORY_BUFFER_DIR'])
    BufferUpdater(state_buffer, headers_cb).run()


def start():
    # Used for testing only; on dc/os $PATH should have gunicorn
    # Have to be in the same folder to run this
    # In case of failure it will not sys.exit
    os.system("gunicorn -c dcos_history_conf.py server:app")
