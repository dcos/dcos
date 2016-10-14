import logging
import os
import sys
import threading


from flask import Flask, Response
from flask.ext.compress import Compress
from history.statebuffer import BufferCollection, BufferUpdater


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


def update():
    BufferUpdater(state_buffer, headers_cb).update()
    update_thread = threading.Timer(2, update)
    update_thread.start()


def create_app():
    app = Flask(__name__)

    logging.basicConfig(format='[%(levelname)s:%(asctime)s] %(message)s', level='INFO')

    compress.init_app(app)

    if 'HISTORY_BUFFER_DIR' not in os.environ:
        sys.exit('HISTORY_BUFFER_DIR must be set!')

    global state_buffer
    state_buffer = BufferCollection(os.environ['HISTORY_BUFFER_DIR'])

    update()

    route(app)

    return app


def home():
    return _response_("history/last - to get the last fetched state\n" +
                      "history/minute - to get the state array of the last minute\n" +
                      "history/hour - to get the state array of the last hour\n" +
                      "ping - to get a pong\n")


def ping():
    return _response_("pong")


def last():
    return _response_(state_buffer.dump('last')[0])


def minute():
    return _buffer_response_('minute')


def hour():
    return _buffer_response_('hour')


def _buffer_response_(name):
    return _response_("[" + ",".join(state_buffer.dump(name)) + "]")


def _response_(content):
    return Response(response=content, content_type="application/json", headers=headers_cb())


def route(app):
    app.add_url_rule('/', view_func=home)
    app.add_url_rule('/ping', view_func=ping)
    app.add_url_rule('/history/last', view_func=last)
    app.add_url_rule('/history/minute', view_func=minute)
    app.add_url_rule('/history/hour', view_func=hour)


def test():
    # Used for unit testing
    app = Flask(__name__)
    route(app)
    return app
