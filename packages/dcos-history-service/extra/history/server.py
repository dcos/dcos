import logging
import os
import sys

from flask import Flask, Response
from flask.ext.compress import Compress
from history.statebuffer import BufferCollection, BufferUpdater

app = Flask(__name__)
compress = Compress()
state_buffer = None


@app.route('/')
def home():
    return _response_("history/last - to get the last fetched state\n" +
                      "history/minute - to get the state array of the last minute\n" +
                      "history/hour - to get the state array of the last hour\n" +
                      "ping - to get a pong\n")


@app.route('/ping')
def ping():
    return "pong"


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
    headers = {
        "Access-Control-Allow-Credentials": "true",
        "Access-Control-Allow-Headers": "accept, accept-charset, accept-encoding, " +
                                        "accept-language, authorization, content-length, " +
                                        "content-type, host, origin, proxy-connection, " +
                                        "referer, user-agent, x-requested-with",
        "Access-Control-Allow-Methods": "HEAD, GET, PUT, POST, PATCH, DELETE",
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Max-Age": "86400"
    }
    return Response(response=content, content_type="application/json", headers=headers)


def start():
    global state_buffer
    logging.basicConfig(format='[%(levelname)s:%(asctime)s] %(message)s', level='INFO')

    compress.init_app(app)

    if 'HISTORY_BUFFER_DIR' not in os.environ:
        sys.exit('HISTORY_BUFFER_DIR must be set!')

    state_buffer = BufferCollection(os.environ['HISTORY_BUFFER_DIR'])
    BufferUpdater(state_buffer).run()
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', '15055')))
