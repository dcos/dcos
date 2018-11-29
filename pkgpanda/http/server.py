"""Pkgpanda HTTP API"""

import http.client
import logging
import os
import sys

from flask import current_app, Flask, jsonify, make_response, request

from pkgpanda import actions, Install, Repository
from pkgpanda.exceptions import (PackageConflict, PackageError,
                                 PackageNotFound, ValidationError)


empty_response = ('', http.client.NO_CONTENT)


def package_listing_response(package_ids):
    return jsonify(sorted(package_ids))


def error_response(message, **kwargs):
    kwargs['error'] = message
    return jsonify(kwargs)


def exception_response(message, exc):
    logging.error(message, exc_info=exc)
    return error_response(message), http.client.INTERNAL_SERVER_ERROR


def invalid_package_id_response(package_id):
    return error_response("Invalid package ID: {}".format(package_id))


def package_not_found_response(package_id):
    return error_response('Package {} not found.'.format(package_id))


def package_response(package_id, repository):
    try:
        package = repository.load(package_id)
    except ValidationError:
        response = (
            invalid_package_id_response(package_id),
            http.client.NOT_FOUND,
        )
    except PackageNotFound:
        response = (
            package_not_found_response(package_id),
            http.client.NOT_FOUND,
        )
    except PackageError:
        error_message = 'Unable to load package {}.'.format(package_id)
        logging.exception(error_message)
        response = (
            error_response(error_message),
            http.client.INTERNAL_SERVER_ERROR,
        )
    else:
        response = (
            jsonify({
                'id': str(package.id),
                'name': str(package.name),
                'version': str(package.version),
            }),
            http.client.OK,
        )

    return response


app = Flask(__name__)
app.config.from_object('pkgpanda.http.config')
app.config.from_envvar('PKGPANDA_HTTP_CONFIG', silent=True)


@app.errorhandler(Exception)
def unexpected_exception_handler(exc):
    return exception_response('An unexpected error has occurred.', exc)


@app.errorhandler(PackageError)
@app.errorhandler(ValidationError)
def uncaught_exception_handler(exc):
    return exception_response(str(exc), exc)


@app.before_request
def set_app_attrs_from_config():
    current_app.install = Install(
        current_app.config['DCOS_ROOT'],
        current_app.config['DCOS_CONFIG_DIR'],
        current_app.config['DCOS_ROOTED_SYSTEMD'],
        manage_systemd=True,
        block_systemd=False,
        manage_state_dir=True,
        state_dir_root=current_app.config['DCOS_STATE_DIR_ROOT'])
    current_app.repository = Repository(
        current_app.config['DCOS_REPO_DIR'])


@app.before_request
def create_work_dir():
    os.makedirs(current_app.config['WORK_DIR'], exist_ok=True)


@app.route('/repository/', methods=['GET'])
def get_package_list():
    return package_listing_response(current_app.repository.list())


@app.route('/repository/<package_id>', methods=['GET'])
def get_package(package_id):
    return package_response(package_id, current_app.repository)


@app.route('/repository/<package_id>', methods=['POST'])
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

    try:
        actions.fetch_package(
            current_app.repository,
            repository_url,
            package_id,
            current_app.config['WORK_DIR'])
    except ValidationError:
        response = (
            invalid_package_id_response(package_id),
            http.client.BAD_REQUEST,
        )
    else:
        response = empty_response

    return response


@app.route('/repository/<package_id>', methods=['DELETE'])
def remove_package(package_id):
    try:
        actions.remove_package(
            current_app.install,
            current_app.repository,
            package_id)
    except PackageNotFound:
        response = (
            package_not_found_response(package_id),
            http.client.NOT_FOUND,
        )
    except PackageConflict:
        response = (
            error_response('Package {} is active, so it can\'t be removed.'),
            http.client.CONFLICT,
        )
    except ValidationError:
        response = (
            invalid_package_id_response(package_id),
            http.client.NOT_FOUND,
        )
    else:
        response = empty_response

    return response


@app.route('/active/', methods=['GET'])
def get_active_package_list():
    return package_listing_response(current_app.install.get_active())


@app.route('/active/<package_id>', methods=['GET'])
def get_active_package(package_id):
    response = make_response(
        package_response(package_id, current_app.repository)
    )

    if response.status_code != http.client.OK:
        return response

    if package_id not in current_app.install.get_active():
        return (
            error_response('Package {} is not active.'.format(package_id)),
            http.client.NOT_FOUND,
        )

    return response


@app.route('/active/', methods=['PUT'])
def activate_packages():
    if not isinstance(request.json, list):
        return (
            error_response(
                'Request body must be a json array of package IDs.'
            ),
            http.client.BAD_REQUEST,
        )

    missing_packages = set(request.json) - set(current_app.repository.list())
    if missing_packages:
        return (
            error_response(
                'Not all packages in the request are present on this node.',
                missing_packages=sorted(missing_packages)
            ),
            http.client.CONFLICT,
        )

    # This will stop all DC/OS services, including this app. Use a web server
    # that supports graceful shutdown to ensure that activation is completed
    # and a response is returned.
    try:
        actions.activate_packages(
            current_app.install,
            current_app.repository,
            request.json,
            systemd=(not current_app.config.get('TESTING')),
            block_systemd=False)
    except ValidationError as exc:
        return error_response(str(exc)), http.client.CONFLICT

    return empty_response


if __name__ == '__main__':
    # TODO(branden): expose app config as cli params
    if '-d' in sys.argv[1:]:
        app.config['DEBUG'] = True
    app.run()
