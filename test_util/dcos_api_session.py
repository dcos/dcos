""" Utilities for interacting with a DC/OS instance via REST API

Most DC/OS deployments will have auth enabled, so this module includes
DcosUser and DcosAuth to be attached to a DcosApiSession. Additionally,
it is sometimes necessary to query specific nodes within a DC/OS cluster,
so there is ARNodeApiClientMixin to allow querying nodes without boilerplate
to set the correct port and scheme.
"""
import copy
import logging
import os
from typing import List, Optional

import requests
import retrying

import test_util.marathon
from test_util.helpers import ApiClientSession, RetryCommonHttpErrorsMixin, Url


class DcosUser:
    """A lightweight user representation for grabbing the auth info and stashing it"""
    def __init__(self, credentials: dict):
        self.credentials = credentials
        self.auth_token = None
        self.auth_cookie = None

    @property
    def auth_header(self):
        return {'Authorization': 'token={}'.format(self.auth_token)}


class DcosAuth(requests.auth.AuthBase):
    def __init__(self, auth_token: str):
        self.auth_token = auth_token

    def __call__(self, request):
        request.headers['Authorization'] = 'token={}'.format(self.auth_token)
        return request


class Exhibitor(RetryCommonHttpErrorsMixin, ApiClientSession):
    def __init__(self, default_url: Url, session: Optional[requests.Session]=None,
                 exhibitor_admin_password: Optional[str]=None):
        super().__init__(default_url)
        if session is not None:
            self.session = session
        if exhibitor_admin_password is not None:
            # Override auth to use HTTP basic auth with the provided admin password.
            self.session.auth = requests.auth.HTTPBasicAuth('admin', exhibitor_admin_password)


class ARNodeApiClientMixin:
    def api_request(self, method, path_extension, *, scheme=None, host=None, query=None,
                    fragment=None, port=None, node=None, **kwargs):
        """ Communicating with a DC/OS cluster is done by default through Admin Router.
        Use this Mixin with an ApiClientSession that requires distinguishing between nodes.
        Admin Router has both a master and agent process and so this wrapper accepts a
        node argument. node must be a host in self.master or self.all_slaves. If given,
        the request will be made to the Admin Router endpoint for that node type
        """
        if node is not None:
            assert port is None, 'node is intended to retrieve port; cannot set both simultaneously'
            assert host is None, 'node is intended to retrieve host; cannot set both simultaneously'
            if node in self.masters:
                # Nothing else to do, master Admin Router uses default HTTP (80) and HTTPS (443) ports
                pass
            elif node in self.all_slaves:
                scheme = scheme if scheme is not None else self.default_url.scheme
                if scheme == 'http':
                    port = 61001
                if scheme == 'https':
                    port = 61002
            else:
                raise Exception('Node {} is not recognized within the DC/OS cluster'.format(node))
            host = node
        return super().api_request(method, path_extension, scheme=scheme, host=host,
                                   query=query, fragment=fragment, port=port, **kwargs)


class DcosApiSession(ARNodeApiClientMixin, RetryCommonHttpErrorsMixin, ApiClientSession):
    def __init__(
            self,
            dcos_url: str,
            masters: Optional[List[str]],
            slaves: Optional[List[str]],
            public_slaves: Optional[List[str]],
            default_os_user: str,
            auth_user: Optional[DcosUser],
            exhibitor_admin_password: Optional[str]=None):
        """Proxy class for DC/OS clusters. If any of the host lists (masters,
        slaves, public_slaves) are provided, the wait_for_dcos function of this
        class will wait until provisioning is complete. If these lists are not
        provided, then there is no ground truth and the cluster will be assumed
        the be in a completed state.

        Args:
            dcos_url: address for the DC/OS web UI.
            masters: list of Mesos master advertised IP addresses.
            slaves: list of Mesos slave/agent advertised IP addresses.
            public_slaves: list of public Mesos slave/agent advertised IP addresses.
            default_os_user: default user that marathon/metronome will launch tasks under
            auth_user: use this user's auth for all requests
                Note: user must be authenticated explicitly or call self.wait_for_dcos()
        """
        super().__init__(Url.from_string(dcos_url))
        self.master_list = masters
        self.slave_list = slaves
        self.public_slave_list = public_slaves
        self.default_os_user = default_os_user
        self.auth_user = auth_user
        self.exhibitor_admin_password = exhibitor_admin_password

    @staticmethod
    def get_args_from_env():
        """ Provides the required arguments for a unauthenticated cluster
        """
        masters = os.getenv('MASTER_HOSTS')
        slaves = os.getenv('SLAVE_HOSTS')
        public_slaves = os.getenv('PUBLIC_SLAVE_HOSTS')
        return {
            'dcos_url': os.getenv('DCOS_DNS_ADDRESS', 'http://leader.mesos'),
            'masters': masters.split(',') if masters else None,
            'slaves': slaves.split(',') if slaves else None,
            'public_slaves': public_slaves.split(',') if public_slaves else None,
            'default_os_user': os.getenv('DCOS_DEFAULT_OS_USER', 'root')}

    @property
    def masters(self):
        return sorted(self.master_list)

    @property
    def slaves(self):
        return sorted(self.slave_list)

    @property
    def public_slaves(self):
        return sorted(self.public_slave_list)

    @property
    def all_slaves(self):
        return sorted(self.slaves + self.public_slaves)

    def set_node_lists_if_unset(self):
        """ Sets the expected cluster topology to be the observed cluster
        topology from exhibitor and mesos. I.E. if masters, slave, or
        public_slaves were not provided, accept whatever is currently available
        """
        if self.master_list is None:
            logging.debug('Master list not provided, setting from exhibitor...')
            r = self.get('/exhibitor/exhibitor/v1/cluster/list')
            r.raise_for_status()
            self.master_list = sorted(r.json()['servers'])
            logging.info('Master list set as: {}'.format(self.masters))
        if self.slave_list is not None and self.public_slave_list is not None:
            return
        r = self.get('/mesos/slaves')
        r.raise_for_status()
        slaves_json = r.json()['slaves']
        if self.slave_list is None:
            logging.debug('Private slave list not provided; fetching from mesos...')
            self.slave_list = sorted(
                [s['hostname'] for s in slaves_json if s['attributes'].get('public_ip') != 'true'])
            logging.info('Private slave list set as: {}'.format(self.slaves))
        if self.public_slave_list is None:
            logging.debug('Public slave list not provided; fetching from mesos...')
            self.public_slave_list = sorted(
                [s['hostname'] for s in slaves_json if s['attributes'].get('public_ip') == 'true'])
            logging.info('Public slave list set as: {}'.format(self.public_slaves))

    @retrying.retry(wait_fixed=2000, stop_max_delay=120 * 1000)
    def _authenticate_default_user(self):
        """retry default auth user because in some deployments,
        the auth endpoint might not be routable immediately
        after Admin Router is up. DcosUser.authenticate()
        will raise exception if authorization fails
        """
        if self.auth_user is None:
            return
        logging.info('Attempting authentication')
        # explicitly use a session with no user authentication for requesting auth headers
        r = self.post('/acs/api/v1/auth/login', json=self.auth_user.credentials, auth=None)
        r.raise_for_status()
        logging.info('Received authentication blob: {}'.format(r.json()))
        self.auth_user.auth_token = r.json()['token']
        self.auth_user.auth_cookie = r.cookies['dcos-acs-auth-cookie']
        logging.info('Authentication successful')
        # Set requests auth
        self.session.auth = DcosAuth(self.auth_user.auth_token)

    @retrying.retry(wait_fixed=1000,
                    retry_on_result=lambda ret: ret is False,
                    retry_on_exception=lambda x: False)
    def _wait_for_marathon_up(self):
        r = self.get('/marathon/ui/')
        # resp_code >= 500 -> backend is still down probably
        if r.status_code < 500:
            logging.info("Marathon is probably up")
            return True
        else:
            msg = "Waiting for Marathon, resp code is: {}"
            logging.info(msg.format(r.status_code))
            return False

    @retrying.retry(wait_fixed=1000)
    def _wait_for_zk_quorum(self):
        """Queries exhibitor to ensure all master ZKs have joined
        """
        r = self.get('/exhibitor/exhibitor/v1/cluster/status')
        if not r.ok:
            logging.warning('Exhibitor status not available')
            r.raise_for_status()
        status = r.json()
        logging.info('Exhibitor cluster status: {}'.format(status))
        zk_nodes = sorted([n['hostname'] for n in status])
        assert zk_nodes == self.masters, 'ZooKeeper has not formed the expected quorum'

    @retrying.retry(wait_fixed=1000,
                    retry_on_result=lambda ret: ret is False,
                    retry_on_exception=lambda x: False)
    def _wait_for_slaves_to_join(self):
        r = self.get('/mesos/master/slaves')
        if r.status_code != 200:
            msg = "Mesos master returned status code {} != 200 "
            msg += "continuing to wait..."
            logging.info(msg.format(r.status_code))
            return False
        data = r.json()
        # Check that there are all the slaves the test knows about. They are all
        # needed to pass the test.
        num_slaves = len(data['slaves'])
        if num_slaves >= len(self.all_slaves):
            msg = "Sufficient ({} >= {}) number of slaves have joined the cluster"
            logging.info(msg.format(num_slaves, self.all_slaves))
            return True
        else:
            msg = "Current number of slaves: {} < {}, continuing to wait..."
            logging.info(msg.format(num_slaves, self.all_slaves))
            return False

    @retrying.retry(wait_fixed=1000,
                    retry_on_result=lambda ret: ret is False,
                    retry_on_exception=lambda x: False)
    def _wait_for_dcos_history_up(self):
        r = self.get('/dcos-history-service/ping')
        # resp_code >= 500 -> backend is still down probably
        if r.status_code <= 500:
            logging.info("DC/OS History is probably up")
            return True
        else:
            msg = "Waiting for DC/OS History, resp code is: {}"
            logging.info(msg.format(r.status_code))
            return False

    @retrying.retry(wait_fixed=1000,
                    retry_on_result=lambda ret: ret is False,
                    retry_on_exception=lambda x: False)
    def _wait_for_dcos_history_data(self):
        ro = self.get('/dcos-history-service/history/last')
        # resp_code >= 500 -> backend is still down probably
        if ro.status_code <= 500:
            logging.info("DC/OS History is probably getting data")
            json = ro.json()
            # if an agent was removed, it may linger in the history data
            assert len(json["slaves"]) >= len(self.all_slaves)
            return True
        else:
            msg = "Waiting for DC/OS History, resp code is: {}"
            logging.info(msg.format(ro.status_code))
            return False

    @retrying.retry(wait_fixed=1000,
                    retry_on_result=lambda ret: ret is False,
                    retry_on_exception=lambda x: False)
    def _wait_for_adminrouter_up(self):
        try:
            # Yeah, we can also put it in retry_on_exception, but
            # this way we will loose debug messages
            self.get('/')
        except requests.ConnectionError as e:
            msg = "Cannot connect to nginx, error string: '{}', continuing to wait"
            logging.info(msg.format(e))
            return False
        else:
            logging.info("Nginx is UP!")
            return True

    # Retry if returncode is False, do not retry on exceptions.
    @retrying.retry(wait_fixed=2000,
                    retry_on_result=lambda r: r is False,
                    retry_on_exception=lambda _: False)
    def _wait_for_srouter_slaves_endpoints(self):
        # Get currently known agents. This request is served straight from
        # Mesos (no AdminRouter-based caching is involved).
        r = self.get('/mesos/master/slaves')
        assert r.status_code == 200

        data = r.json()
        # only check against the slaves we expect to be in the cluster
        # so we can check that cluster has returned after a failure
        # in which case will will have new slaves and dead slaves
        slaves_ids = sorted(x['id'] for x in data['slaves'] if x['hostname'] in self.all_slaves)

        for slave_id in slaves_ids:
            # AdminRouter's slave endpoint internally uses cached Mesos
            # state data. That is, slave IDs of just recently joined
            # slaves can be unknown here. For those, this endpoint
            # returns a 404. Retry in this case, until this endpoint
            # is confirmed to work for all known agents.
            uri = '/slave/{}/slave%281%29/state.json'.format(slave_id)
            r = self.get(uri)
            if r.status_code == 404:
                return False
            assert r.status_code == 200
            data = r.json()
            assert "id" in data
            assert data["id"] == slave_id

    @retrying.retry(wait_fixed=2000,
                    retry_on_result=lambda r: r is False,
                    retry_on_exception=lambda _: False)
    def _wait_for_metronome(self):
        r = self.get('/service/metronome/v1/jobs')
        # 500 and 504 are the expected behavior of a service
        # backend that is not up and running.
        if r.status_code == 500 or r.status_code == 504:
            logging.info("Metronome gateway timeout, continue waiting for backend...")
            return False
        assert r.status_code == 200

    def wait_for_dcos(self):
        self._wait_for_adminrouter_up()
        self._authenticate_default_user()
        self.set_node_lists_if_unset()
        self._wait_for_marathon_up()
        self._wait_for_zk_quorum()
        self._wait_for_slaves_to_join()
        self._wait_for_dcos_history_up()
        self._wait_for_srouter_slaves_endpoints()
        self._wait_for_dcos_history_data()
        self._wait_for_metronome()

    def copy(self):
        """ Create a new client session without cookies, with the authentication intact.
        """
        new = copy.deepcopy(self)
        new.session.cookies.clear()
        return new

    def get_user_session(self, user):
        """Returns a copy of this client but with auth for user (can be None)
        """
        new = self.copy()
        new.session.auth = None
        new.auth_user = None
        if user is not None:
            new.auth_user = user
            new._authenticate_default_user()
        return new

    @property
    def exhibitor(self):
        if self.exhibitor_admin_password is None:
            # No basic HTTP auth. Access Exhibitor via the adminrouter.
            default_url = self.default_url.copy(path='exhibitor')
        else:
            # Exhibitor is protected with HTTP basic auth, which conflicts with adminrouter's auth. We must bypass
            # the adminrouter and access Exhibitor directly.
            default_url = Url.from_string('http://{}:8181'.format(self.masters[0]))

        return Exhibitor(
            default_url=default_url,
            session=self.copy().session,
            exhibitor_admin_password=self.exhibitor_admin_password)

    @property
    def marathon(self):
        return test_util.marathon.Marathon(
            default_url=self.default_url.copy(path='marathon'),
            default_os_user=self.default_os_user,
            session=self.copy().session)

    @property
    def metronome(self):
        new = self.copy()
        new.default_url = self.default_url.copy(path='service/metronome/v1')
        return new

    @property
    def health(self):
        new = self.copy()
        new.default_url = self.default_url.copy(query='cache=0', path='system/health/v1')
        return new

    @property
    def logs(self):
        new = self.copy()
        new.default_url = self.default_url.copy(path='system/v1/logs')
        return new

    @property
    def metrics(self):
        new = self.copy()
        new.default_url = self.default_url.copy(path='/system/v1/metrics/v0')
        return new

    def metronome_one_off(self, job_definition, timeout=300, ignore_failures=False):
        """Run a job on metronome and block until it returns success
        """
        job_id = job_definition['id']

        @retrying.retry(wait_fixed=2000, stop_max_delay=timeout * 1000,
                        retry_on_result=lambda ret: not ret,
                        retry_on_exception=lambda x: False)
        def wait_for_completion():
            r = self.metronome.get('jobs/' + job_id, params={'embed': 'history'})
            r.raise_for_status()
            out = r.json()
            if not ignore_failures and (out['history']['failureCount'] != 0):
                raise Exception('Metronome job failed!: ' + repr(out))
            if out['history']['successCount'] != 1:
                logging.info('Waiting for one-off to finish. Status: ' + repr(out))
                return False
            logging.info('Metronome one-off successful')
            return True
        logging.info('Creating metronome job: ' + repr(job_definition))
        r = self.metronome.post('jobs', json=job_definition)
        r.raise_for_status()
        logging.info('Starting metronome job')
        r = self.metronome.post('jobs/{}/runs'.format(job_id))
        r.raise_for_status()
        wait_for_completion()
        logging.info('Deleting metronome one-off')
        r = self.metronome.delete('jobs/' + job_id)
        r.raise_for_status()

    def mesos_sandbox_directory(self, slave_id, framework_id, task_id):
        r = self.get('/agent/{}/state'.format(slave_id))
        r.raise_for_status()
        agent_state = r.json()

        try:
            framework = next(f for f in agent_state['frameworks'] if f['id'] == framework_id)
        except StopIteration:
            raise Exception('Framework {} not found on agent {}'.format(framework_id, slave_id))

        try:
            executor = next(e for e in framework['executors'] if e['id'] == task_id)
        except StopIteration:
            raise Exception('Executor {} not found on framework {} on agent {}'.format(task_id, framework_id, slave_id))

        return executor['directory']

    def mesos_sandbox_file(self, slave_id, framework_id, task_id, filename):
        r = self.get(
            '/agent/{}/files/download'.format(slave_id),
            params={'path': self.mesos_sandbox_directory(slave_id, framework_id, task_id) + '/' + filename}
        )
        r.raise_for_status()
        return r.text

    def get_version(self):
        version_metadata = self.get('/dcos-metadata/dcos-version.json')
        version_metadata.raise_for_status()
        data = version_metadata.json()
        return data["version"]
