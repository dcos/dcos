import asyncio
import glob
import importlib
import json
import logging
import os

import pkg_resources
from aiohttp import web

import dcos_installer
import gen.calc
from dcos_installer import backend
from dcos_installer.constants import STATE_DIR

from ssh.ssh_runner import Node


log = logging.getLogger()

options = None

VERSION = '1'

ui_dist_path = os.getenv('INSTALLER_UI_PATH', pkg_resources.resource_filename(__name__, 'templates/'))
index_path = '{}index.html'.format(ui_dist_path)
assets_path = '{}assets/'.format(ui_dist_path)

# Dict containing action name to handler mappings.
action_map = {
    'preflight': dcos_installer.action_lib.run_preflight,
    'deploy': dcos_installer.action_lib.install_dcos,
    'postflight': dcos_installer.action_lib.run_postflight,
}

remove_on_done = ['preflight', 'postflight']

# TODO(cmaloney): Kill this. Should store somewhere proper
current_action = ""


def root(request):
    """Return the root endpoint, serve the index.html.

    :param request: a web requeest object.
    :type request: request | None
    """
    log.info("Root page requested.")
    index_file = open(index_path)
    log.info("Serving %s", index_path)
    resp = web.Response(body=index_file.read().encode('utf-8'))
    resp.headers['content-type'] = 'text/html'
    return resp


def redirect_to_root(request):
    """Return the redirect from /api/v1 to /

    :param request: a web requeest object.
    :type request: request | None
    """
    log.warning("/api/v{} -> redirecting -> /".format(VERSION))
    return web.HTTPFound('/'.format(VERSION))


def get_version(args):
    resp = web.json_response({'version': gen.calc.entry['must']['dcos_version']})
    resp.headers['Content-Type'] = 'application/json'
    return resp


def configure(request):
    """Return /api/v1/configure

    :param request: a web requeest object.
    :type request: request | None
    """
    if request.method == 'POST':
        new_config = yield from request.json()
        log.info('POST to configure: {}'.format(new_config))
        validation_err, messages = backend.create_config_from_post(new_config)

        resp = web.json_response({}, status=200)
        if validation_err:
            resp = web.json_response(messages, status=400)

        return resp

    elif request.method == 'GET':
        config = backend.get_ui_config()
        resp = web.json_response(config)

    resp.headers['Content-Type'] = 'application/json'
    return resp


def configure_status(request):
    """Return /configure/status

    :param request: a web requeest object.
    :type request: request | None
    """
    log.info("Request for configuration validation made.")
    code = 200
    messages = backend.do_validate_config()
    if messages:
        code = 400
    resp = web.json_response(messages, status=code)
    return resp


def configure_type(request):
    """Return /configure/type

    :param request: a web requeest object.
    :type request: request | None
    """
    log.info("Request for configuration type made.")
    return web.json_response(backend.determine_config_type())


def success(request):
    """Return /success

    :param request: a web requeest object.
    :type request: request | None
    """
    log.info("Request for success made.")
    msgs, code = backend.success()
    return web.json_response(msgs, status=code)


def unlink_state_file(action_name):
    json_status_file = STATE_DIR + '/{}.json'.format(action_name)
    if os.path.isfile(json_status_file):
        log.debug('removing {}'.format(json_status_file))
        os.unlink(json_status_file)
        return True
    log.debug('cannot remove {}, file not found'.format(json_status_file))
    return False


def read_json_state(action_name):
    json_status_file = STATE_DIR + '/{}.json'.format(action_name)
    if not os.path.isfile(json_status_file):
        return False

    with open(json_status_file) as fh:
        return json.load(fh)


def action_action_name(request):
    """Return /action/<action_name>

    :param request: a web requeest object.
    :type request: request | None
    """
    global current_action
    action_name = request.match_info['action_name']

    # Update the global action
    json_state = read_json_state(action_name)
    current_action = action_name

    if request.method == 'GET':
        log.info('GET {}'.format(action_name))

        if json_state:
            return web.json_response(json_state)
        return web.json_response({})

    elif request.method == 'POST':
        log.info('POST {}'.format(action_name))
        action = action_map.get(action_name)
        # If the action name is preflight, attempt to run configuration
        # generation. If genconf fails, present the UI with a usable error
        # for the end-user
        if action_name == 'preflight':
            try:
                log.warning("GENERATING CONFIGURATION")
                backend.do_configure()
            except:
                genconf_failure = {
                    "errors": "Configuration generation failed, please see command line for details"
                }
                return web.json_response(genconf_failure, status=400)

        params = yield from request.post()

        if json_state:
            if action_name == 'deploy' and 'retry' in params:
                if 'hosts' in json_state:
                    failed_hosts = []
                    for deploy_host, deploy_params in json_state['hosts'].items():
                        if deploy_params['host_status'] != 'success':
                            failed_hosts.append(Node(deploy_host, tags=deploy_params['tags']))
                    log.debug('failed hosts: {}'.format(failed_hosts))
                    if failed_hosts:
                        yield from asyncio.async(
                            action(
                                backend.get_config(),
                                state_json_dir=STATE_DIR,
                                hosts=failed_hosts,
                                try_remove_stale_dcos=True,
                                **params))
                        return web.json_response({
                            'status': 'retried',
                            'details': sorted(['{}:{}'.format(node.ip, node.port) for node in failed_hosts])
                        })

            if action_name not in remove_on_done:
                return web.json_response({'status': '{} was already executed, skipping'.format(action_name)})

            running = False
            for host, attributes in json_state['hosts'].items():
                if attributes['host_status'].lower() == 'running':
                    running = True

            log.debug('is action running: {}'.format(running))
            if running:
                return web.json_response({'status': '{} is running, skipping'.format(action_name)})
            else:
                unlink_state_file(action_name)

        yield from asyncio.async(action(backend.get_config(), state_json_dir=STATE_DIR, options=options, **params))
        return web.json_response({'status': '{} started'.format(action_name)})


def action_current(request):
    """Return the current action /action/current endpoint.

    :param request: a web requeest object.
    :type request: request | None
    """
    return web.json_response({'current_action': current_action})


def logs_handler(request):
    """Return the log file on disk.

    :param request: a web requeest object.
    :type request: request | None
    """
    log.info("Request for logs endpoint made.")
    complete_log_path = '/genconf/state/complete.log'
    json_files = glob.glob('/genconf/state/*.json')
    complete_log = []
    for f in json_files:
        log.debug('Adding {} to complete log file.'.format(f))
        with open(f) as blob:
            complete_log.append(json.loads(blob.read()))

    with open(complete_log_path, 'w') as f:
        f.write(json.dumps(complete_log, indent=4, sort_keys=True))

    return web.HTTPFound('/download/log/complete.log'.format(VERSION))


def no_caching(request, response):
    response.headers['Cache-Control'] = 'no-cache'


def build_app(loop):
    """Define the aiohttp web application framework and setup the routes to be used in the API"""
    global current_action

    app = web.Application(loop=loop)

    current_action = ''

    app.router.add_route('GET', '/', root)
    app.router.add_route('GET', '/api/v{}'.format(VERSION), redirect_to_root)
    app.router.add_route('GET', '/api/v{}/version'.format(VERSION), get_version)
    app.router.add_route('GET', '/api/v{}/configure'.format(VERSION), configure)
    app.router.add_route('POST', '/api/v{}/configure'.format(VERSION), configure)
    app.router.add_route('GET', '/api/v{}/configure/status'.format(VERSION), configure_status)
    app.router.add_route('GET', '/api/v{}/configure/type'.format(VERSION), configure_type)
    app.router.add_route('GET', '/api/v{}/success'.format(VERSION), success)
    # TODO(malnick) The regex handling in the variable routes blows up if we insert another variable to be
    # filled in by .format. Had to hardcode the VERSION into the URL for now. Fix suggestions please!
    app.router.add_route('GET', '/api/v1/action/{action_name:preflight|postflight|deploy}', action_action_name)
    app.router.add_route('POST', '/api/v1/action/{action_name:preflight|postflight|deploy}', action_action_name)
    app.router.add_route('GET', '/api/v{}/action/current'.format(VERSION), action_current)
    app.router.add_route('GET', '/api/v{}/logs'.format(VERSION), logs_handler)

    # TODO(cmaloney): These should probably actually hard fail.
    try:
        app.router.add_static('/assets', assets_path)
        app.router.add_static('/download/log', '/genconf/state/')
    except ValueError as err:
        log.warning(err)

    # Allow overriding calculators with a `gen_extra/async_server.py` if it exists
    if os.path.exists('gen_extra/async_server.py'):
        mod = importlib.machinery.SourceFileLoader('gen_extra.async_server', 'gen_extra/async_server.py').load_module()
        mod.extend_app(app)

    app.on_response_prepare.append(no_caching)

    return app


def start(cli_options):
    global options
    options = cli_options

    log.debug('DC/OS Installer')
    loop = asyncio.get_event_loop()
    app = build_app(loop)
    handler = app.make_handler()
    f = loop.create_server(
        handler,
        '0.0.0.0',
        cli_options.port)
    srv = loop.run_until_complete(f)
    log.info('Starting server {}'.format(srv.sockets[0].getsockname()))
    if os.path.isdir(STATE_DIR):
        for state_file in glob.glob(STATE_DIR + '/*.json'):
            try:
                os.unlink(state_file)
                log.debug('removing {}'.format(state_file))
            except FileNotFoundError:
                log.error('{} not found'.format(state_file))
            except PermissionError:
                log.error('cannot remove {}, Permission denied'.format(state_file))
    else:
        os.makedirs(STATE_DIR)

    assert os.path.isdir(assets_path)
    assert os.path.isdir('/genconf/state/')

    try:
        loop.run_forever()
    except KeyboardInterrupt:
        srv.close()
        loop.run_until_complete(handler.finish_connections(1.0))
        loop.run_until_complete(app.finish())
    loop.close()
