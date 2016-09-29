import logging
import os
import sys
import asyncio

from history.statebuffer import BufferCollection, BufferUpdater
from aiohttp import web


app = web.Application()
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


def home(request):
    return _response_("history/last - to get the last fetched state\n" +
                      "history/minute - to get the state array of the last minute\n" +
                      "history/hour - to get the state array of the last hour\n" +
                      "ping - to get a pong\n")


def ping(request):
    return _response_("pong")


def last(request):
    return _response_(state_buffer.dump('last')[0])


def minute(request):
    return _buffer_response_('minute')


def hour(request):
    return _buffer_response_('hour')


def _buffer_response_(name):
    return _response_("[" + ",".join(state_buffer.dump(name)) + "]")


def _response_(content):
    resp = web.json_response(content, headers=headers_cb())
    resp.enable_compression()
    return resp


def build_app(loop):
    app = web.Application(loop=loop)

    app.router.add_route('GET', '/', home)
    app.router.add_route('GET', '/ping', ping)
    app.router.add_route('GET', '/history/last', last)
    app.router.add_route('GET', '/history/minute', minute)
    app.router.add_route('GET', '/history/hour', hour)

    return app


@asyncio.coroutine
def buff_update(loop):
    BufferUpdater(state_buffer, headers_cb())
    #yield from asyncio.sleep(2)
    #loop.call_later(2, buff_update(loop), loop)



def start():
    global state_buffer

    logging.basicConfig(format='[%(levelname)s:%(asctime)s] %(message)s', level='INFO')

    if 'HISTORY_BUFFER_DIR' not in os.environ:
        sys.exit('HISTORY_BUFFER_DIR must be set!')

    state_buffer = BufferCollection(os.environ['HISTORY_BUFFER_DIR'])


    loop = asyncio.get_event_loop()
    app = build_app(loop)
    handler = app.make_handler()
    f = loop.create_server(handler, '0.0.0.0', 15055)
    srv = loop.run_until_complete(f)

    try:
            loop.call_soon(buff_update(loop), loop)
            loop.run_forever()
    finally:
        srv.close()
        loop.run_until_complete(app.shutdown())
        loop.run_until_complete(handler.finish_connections(1.0))
        loop.run_until_complete(app.cleanup())
        loop.run_until_complete(srv.wait_closed())

    loop.close()


