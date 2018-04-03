import asyncio
import glob
import importlib
import json
import logging
import os
import sys

import pkg_resources
from aiohttp import web

import dcos_installer.action_lib
import gen.calc
import pkgpanda.util
from dcos_installer import backend
from dcos_installer.config import Config, make_default_config_if_needed
from dcos_installer.constants import CONFIG_PATH, IP_DETECT_PATH, SSH_KEY_PATH, STATE_DIR
from pkgpanda.util import is_windows
try:
    from ssh.runner import Node
except ImportError:
    pass

if not is_windows:
    assert 'ssh.runner' in sys.modules and 'Node' in globals()

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


def try_read_file(path):
    if os.path.isfile(path):
        return pkgpanda.util.load_string(path)
    return None


def extract_external(post_data, start_key, dest_key, filename, mode) -> dict:
    if start_key not in post_data:
        return post_data

    value = post_data[start_key]
    if not value:
        log.warning('Skipping write {} to {} because it looked empty.'.format(value, filename))
        return post_data

    log.warning('Writing {}'.format(filename))
    pkgpanda.util.write_string(filename, value)
    os.chmod(filename, mode)
    del post_data[start_key]
    post_data[dest_key] = filename
    return post_data


def configure(request):
    """Return /api/v1/configure

    :param request: a web requeest object.
    :type request: request | None
    """
    if request.method == 'POST':
        new_config = yield from request.json()

        # Save ssh_key, ip_detect as needed
        # TODO(cmaloney): make ssh_key derive from ssh_key_path so we can just set ssh_key and skip all this.
        new_config = extract_external(new_config, 'ssh_key', 'ssh_key_path', SSH_KEY_PATH, 0o600)
        # TODO(cmaloney): change this to ip_detect_contents removing the need for the remapping.
        new_config = extract_external(new_config, 'ip_detect_script', 'ip_detect_path', IP_DETECT_PATH, 0o644)

        log.info('POST to configure: {}'.format(new_config))
        messages = backend.create_config_from_post(new_config, CONFIG_PATH)

        # Map  back to DC/OS UI configuration parameters.
        # TODO(cmaloney): Remove need to remap validation keys. The remapping is making things show up
        # under the key of the user config chunk that caused them rather than their particular key so
        # num_masters validation for instance shows up under master_list where the user would expect it.
        if "ssh_key_path" in messages:
            messages["ssh_key"] = messages["ssh_key_path"]

        if "ip_detect_contents" in messages:
            messages['ip_detect_path'] = messages['ip_detect_contents']

        if 'num_masters' in messages:
            messages['master_list'] = messages['num_masters']

        resp = web.json_response({}, status=200)
        if messages:
            resp = web.json_response(messages, status=400)

        return resp

    elif request.method == 'GET':
        config = Config(CONFIG_PATH).config
        # TODO(cmaloney): should exclude the value entirely if the file doesn't exist.
        config['ssh_key'] = try_read_file(SSH_KEY_PATH)
        config['ip_detect_script'] = try_read_file(IP_DETECT_PATH)
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
    messages = Config(CONFIG_PATH).do_validate(include_ssh=True)
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
    msgs, code = backend.success(Config(CONFIG_PATH))
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
                            failed_hosts.append(Node(
                                deploy_host, tags=deploy_params['tags'],
                                default_port=int(Config(CONFIG_PATH).hacky_default_get('ssh_port', 22))))
                    log.debug('failed hosts: {}'.format(failed_hosts))
                    if failed_hosts:
                        yield from asyncio.async(
                            action(
                                Config(CONFIG_PATH),
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

        yield from asyncio.async(action(Config(CONFIG_PATH), state_json_dir=STATE_DIR, options=options, **params))
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
    complete_log_path = STATE_DIR + '/complete.log'
    json_files = glob.glob(STATE_DIR + '/*.json')
    complete_log = []
    for f in json_files:
        log.debug('Adding {} to complete log file.'.format(f))
        with open(f) as blob:
            complete_log.append(json.loads(blob.read()))

    with open(complete_log_path, 'w') as f:
        f.write(json.dumps(complete_log, indent=4, sort_keys=True))

    return web.HTTPFound('/download/log/complete.log'.format(VERSION))


def build_app(loop):
    """Define the aiohttp web application framework and setup the routes to be used in the API"""
    global current_action

    app = web.Application(loop=loop)

    current_action = ''

    # Disable all caching for everything, disable once the Web UI gets cache
    # breaking urls for it's assets (still need to not cache the REST responses, index.html though)
    # TODO(cmaloney): Python 3.6 switch this to `async def` per:
    #                 http://aiohttp.readthedocs.io/en/stable/web.html#signals
    def no_caching(request, response):
        response.headers['Cache-Control'] = 'no-store, must-revalidate'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '0'
    app.on_response_prepare.append(no_caching)

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
        # Passing an absolute path because we don't trust add_static() to resolve relative paths for us.
        app.router.add_static('/assets', os.path.abspath(assets_path))
        app.router.add_static('/download/log', os.path.abspath(STATE_DIR))
    except ValueError as err:
        log.warning(err)

    # Allow overriding calculators with a `gen_extra/async_server.py` if it exists
    if os.path.exists('gen_extra/async_server.py'):
        mod = importlib.machinery.SourceFileLoader('gen_extra.async_server', 'gen_extra/async_server.py').load_module()
        mod.extend_app(app)

    return app


def start(cli_options):
    global options
    options = cli_options

    log.debug('DC/OS Installer')
    make_default_config_if_needed(CONFIG_PATH)
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
    assert os.path.isdir(STATE_DIR)

    try:
        loop.run_forever()
    except KeyboardInterrupt:
        srv.close()
        loop.run_until_complete(handler.finish_connections(1.0))
        loop.run_until_complete(app.finish())
    loop.close()
