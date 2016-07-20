"""Pkgpanda HTTP API"""

import http.client
import sys

from flask import Flask, abort, current_app, json, request

from pkgpanda import Install, Repository, actions

empty_response = ('', http.client.NO_CONTENT)


def package_index(packages, package_id=None):
    if package_id is None:
        return json.dumps(sorted(packages))
    elif package_id in packages:
        return empty_response
    else:
        abort(http.client.NOT_FOUND)


app = Flask(__name__)
app.config.from_object('pkgpanda.http.config')
app.config.from_envvar('PKGPANDA_HTTP_CONFIG', silent=True)


@app.before_request
def set_app_attrs_from_config():
    current_app.install = Install(
        current_app.config['DCOS_ROOT'],
        current_app.config['DCOS_CONFIG_DIR'],
        current_app.config['DCOS_ROOTED_SYSTEMD'],
        manage_systemd=True,
        block_systemd=False)
    current_app.repository = Repository(
        current_app.config['DCOS_REPO_DIR'])


@app.route('/', methods=['GET'])
@app.route('/<package_id>', methods=['GET'])
def get_package(package_id=None):
    return package_index(current_app.repository.list(), package_id)


@app.route('/<package_id>', methods=['POST'])
def fetch_package(package_id):
    try:
        repository_url = request.json['repository_url']
    except Exception:
        abort(http.client.BAD_REQUEST)

    actions.fetch_package(
        current_app.repository,
        repository_url,
        package_id,
        current_app.config['WORK_DIR'])

    return empty_response


@app.route('/<package_id>', methods=['DELETE'])
def remove_package(package_id):
    if package_id not in current_app.repository.list():
        abort(http.client.NOT_FOUND)
    if package_id in current_app.install.get_active():
        abort(http.client.CONFLICT)
    actions.remove_package(
        current_app.install,
        current_app.repository,
        package_id)
    return empty_response


@app.route('/active/', methods=['GET'])
@app.route('/active/<package_id>', methods=['GET'])
def get_active_package(package_id=None):
    return package_index(current_app.install.get_active(), package_id)


@app.route('/active/', methods=['PUT'])
def activate_packages():
    if not isinstance(request.json, list):
        abort(http.client.BAD_REQUEST)
    # All packages in the request body must be present in the repository.
    if not (set(request.json) <= set(current_app.repository.list())):
        abort(http.client.CONFLICT)

    # This will stop all DC/OS services, including this app. Use a web server
    # that supports graceful shutdown to ensure that activation is completed
    # and a response is returned.
    actions.activate_packages(
        current_app.install,
        current_app.repository,
        request.json,
        systemd=(not current_app.config.get('TESTING')),
        block_systemd=False)

    return empty_response


if __name__ == '__main__':
    # TODO(branden): expose app config as cli params
    if '-d' in sys.argv[1:]:
        app.config['DEBUG'] = True
    app.run()
