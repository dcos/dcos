"""Pkgpanda HTTP API"""

import http.client
import logging
import sys

from flask import Flask, current_app, jsonify, request

from pkgpanda import Install, Repository, actions
from pkgpanda.exceptions import PackageError


empty_response = ('', http.client.NO_CONTENT)


def package_listing_response(package_ids):
    return jsonify(sorted(package_ids))


def package_response(package_id, repository):
    try:
        package = repository.load(package_id)
    except PackageError:
        error_message = 'Unable to load package {}.'.format(package_id)
        logging.exception(error_message)
        return error_response(error_message), http.client.INTERNAL_SERVER_ERROR

    return jsonify({
        'id': str(package.id),
        'name': str(package.name),
        'version': str(package.version),
    })


def error_response(message):
    return jsonify({'error': message})


app = Flask(__name__)
app.config.from_object('pkgpanda.http.config')
app.config.from_envvar('PKGPANDA_HTTP_CONFIG', silent=True)


@app.errorhandler(Exception)
def uncaught_exception_handler(exc):
    error_message = 'An unexpected error has occurred.'
    logging.error(error_message, exc_info=exc)
    return error_response(error_message), http.client.INTERNAL_SERVER_ERROR


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
def get_package_list():
    return package_listing_response(current_app.repository.list())


@app.route('/<package_id>', methods=['GET'])
def get_package(package_id):
    if not current_app.repository.has_package(package_id):
        return (
            error_response('Package {} not found.'.format(package_id)),
            http.client.NOT_FOUND,
        )
    return package_response(package_id, current_app.repository)


@app.route('/<package_id>', methods=['POST'])
def fetch_package(package_id):
    try:
        repository_url = request.json['repository_url']
    except Exception:
        return (
            error_response(
                'Request body must be a json object with a `repository_url` '
                'key.'
            ),
            http.client.BAD_REQUEST,
        )

    actions.fetch_package(
        current_app.repository,
        repository_url,
        package_id,
        current_app.config['WORK_DIR'])

    return empty_response


@app.route('/<package_id>', methods=['DELETE'])
def remove_package(package_id):
    if not current_app.repository.has_package(package_id):
        return (
            error_response('Package {} not found.'.format(package_id)),
            http.client.NOT_FOUND,
        )
    if package_id in current_app.install.get_active():
        return (
            error_response('Package {} is active, so it can\'t be removed.'),
            http.client.CONFLICT,
        )
    actions.remove_package(
        current_app.install,
        current_app.repository,
        package_id)
    return empty_response


@app.route('/active/', methods=['GET'])
def get_active_package_list():
    return package_listing_response(current_app.install.get_active())


@app.route('/active/<package_id>', methods=['GET'])
def get_active_package(package_id):
    if package_id not in current_app.install.get_active():
        return (
            error_response('Package {} is not active.'.format(package_id)),
            http.client.NOT_FOUND,
        )

    return package_response(package_id, current_app.repository)


@app.route('/active/', methods=['PUT'])
def activate_packages():
    if not isinstance(request.json, list):
        return (
            error_response(
                'Request body must be a json array of package IDs.'
            ),
            http.client.BAD_REQUEST,
        )
    if not (set(request.json) <= set(current_app.repository.list())):
        return (
            error_response('Not all packages in the request are present.'),
            http.client.CONFLICT,
        )

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
