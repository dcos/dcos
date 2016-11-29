import copy
import logging
import os
from urllib.parse import urlparse

import dns.exception
import dns.resolver
import requests
import retrying

import test_util.helpers
import test_util.marathon

ADMINROUTER_PORT_MAPPING = {
    'master': {'http': 80, 'https': 443},
    'agent': {'http': 61001, 'https': 61002}}


def get_args_from_env():
    """Does basic sanity checks and returns args converted
    from strings to python data types
    """
    assert 'DCOS_DNS_ADDRESS' in os.environ
    assert 'MASTER_HOSTS' in os.environ
    assert 'PUBLIC_MASTER_HOSTS' in os.environ
    assert 'SLAVE_HOSTS' in os.environ
    assert 'PUBLIC_SLAVE_HOSTS' in os.environ
    assert 'DNS_SEARCH' in os.environ
    assert 'DCOS_PROVIDER' in os.environ

    # must be true or false (prevents misspellings)
    assert os.environ['DNS_SEARCH'] in ['true', 'false']

    assert os.environ['DCOS_PROVIDER'] in ['onprem', 'aws', 'azure']

    return {
        'dcos_url': os.environ['DCOS_DNS_ADDRESS'],
        'masters': os.environ['MASTER_HOSTS'].split(','),
        'public_masters': os.environ['PUBLIC_MASTER_HOSTS'].split(','),
        'slaves': os.environ['SLAVE_HOSTS'].split(','),
        'public_slaves': os.environ['PUBLIC_SLAVE_HOSTS'].split(','),
        'dns_search_set': os.environ['DNS_SEARCH'] == 'true',
        'provider': os.environ['DCOS_PROVIDER'],
        'auth_enabled': os.getenv('DCOS_AUTH_ENABLED', 'true') == 'true',
        'default_os_user': os.getenv('DCOS_DEFAULT_OS_USER', 'root'),
        'ca_cert_path': os.getenv('DCOS_CA_CERT_PATH', None)}


class ClusterApi(test_util.helpers.ApiClient):

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
            assert len(json["slaves"]) == len(self.all_slaves)
            return True
        else:
            msg = "Waiting for DC/OS History, resp code is: {}"
            logging.info(msg.format(ro.status_code))
            return False

    @retrying.retry(wait_fixed=1000,
                    retry_on_result=lambda ret: ret is False,
                    retry_on_exception=lambda x: False)
    def _wait_for_leader_election(self):
        mesos_resolver = dns.resolver.Resolver()
        mesos_resolver.nameservers = self.public_masters
        mesos_resolver.port = 61053
        try:
            # Yeah, we can also put it in retry_on_exception, but
            # this way we will loose debug messages
            mesos_resolver.query('leader.mesos', 'A')
        except dns.exception.DNSException as e:
            msg = "Cannot resolve leader.mesos, error string: '{}', continuing to wait"
            logging.info(msg.format(e))
            return False
        else:
            logging.info("leader.mesos dns entry is UP!")
            return True

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
        self._wait_for_leader_election()
        self._wait_for_adminrouter_up()
        if self.auth_enabled and self.web_auth_default_user:
            self._authenticate_default_user()
        self._wait_for_marathon_up()
        self._wait_for_zk_quorum()
        self._wait_for_slaves_to_join()
        self._wait_for_dcos_history_up()
        self._wait_for_srouter_slaves_endpoints()
        self._wait_for_dcos_history_data()
        self._wait_for_metronome()

    @retrying.retry(wait_fixed=2000, stop_max_delay=120 * 1000)
    def _authenticate_default_user(self):
        """retry default auth user because in some deployments,
        the auth endpoint might not be routable immediately
        after adminrouter is up. DcosUser.authenticate()
        will raise exception if authorization fails
        """
        self.web_auth_default_user.authenticate(self)
        self.default_headers.update(self.web_auth_default_user.auth_header)

    def __init__(self, dcos_url, masters, public_masters, slaves, public_slaves,
                 dns_search_set, provider, auth_enabled, default_os_user,
                 web_auth_default_user=None, ca_cert_path=None):
        """Proxy class for DC/OS clusters.

        Args:
            dcos_url: address for the DC/OS web UI.
            masters: list of Mesos master advertised IP addresses.
            public_masters: list of Mesos master IP addresses routable from
                the local host.
            slaves: list of Mesos slave/agent advertised IP addresses.
            dns_search_set: string indicating that a DNS search domain is
                configured if its value is "true".
            provider: onprem, azure, or aws
            auth_enabled: True or False
            default_os_user: default user that marathon/metronome will launch tasks under
            web_auth_default_user: if auth_enabled, use this user's auth for all requests
                Note: user must be authenticated explicitly or call self.wait_for_dcos()
            ca_cert_path: (str) optional path point to the CA cert to make requests against
        """
        # URL must include scheme
        assert dcos_url.startswith('http')
        parse_result = urlparse(dcos_url)
        self.scheme = parse_result.scheme
        self.dns_host = parse_result.netloc.split(':')[0]

        # Make URL never end with /
        self.dcos_url = dcos_url.rstrip('/')

        super().__init__(
            default_host_url=self.dcos_url,
            api_base=None,
            ca_cert_path=ca_cert_path,
            get_node_url=self.get_node_url)
        self.masters = sorted(masters)
        self.public_masters = sorted(public_masters)
        self.slaves = sorted(slaves)
        self.public_slaves = sorted(public_slaves)
        self.all_slaves = sorted(slaves + public_slaves)
        self.zk_hostports = ','.join(':'.join([host, '2181']) for host in self.public_masters)
        self.dns_search_set = dns_search_set
        self.provider = provider
        self.auth_enabled = auth_enabled
        self.default_os_user = default_os_user
        self.web_auth_default_user = web_auth_default_user

        assert len(self.masters) == len(self.public_masters)

    def get_user_session(self, user):
        """Returns a copy of self with auth headers set for user
        """
        new_session = copy.deepcopy(self)
        # purge old auth headers
        if self.web_auth_default_user is not None:
            for k in self.web_auth_default_user.auth_header.keys():
                if k in new_session.default_headers:
                    del new_session.default_headers[k]
        # if user is given then auth and update the headers
        new_session.web_auth_default_user = user
        if user is not None:
            new_session._authenticate_default_user()
        return new_session

    def get_node_url(self, node, port=None):
        """
        Args:
            node: (str) the hostname of the node to be requested from, if node=None,
                then public cluster address (see environment DCOS_DNS_ADDRESS)
            port: (int) port to be requested at. If port=None, the default port
                for that given node type will be used
        Returns:
            fully-qualified URL string for this API
        """
        if node in self.masters:
            role = 'master'
        elif node in self.all_slaves:
            role = 'agent'
        else:
            raise Exception('Node {} is not recognized within the DC/OS cluster'.format(node))
        if port is None:
            port = ADMINROUTER_PORT_MAPPING[role][self.scheme]
        # do not explicitly declare default ports
        if (port == 80 and self.scheme == 'http') or (port == 443 and self.scheme == 'https'):
            netloc = node
        else:
            netloc = '{}:{}'.format(node, port)
        return '{}://{}'.format(self.scheme, netloc)

    @property
    def marathon(self):
        marathon_client = test_util.marathon.Marathon(
            default_host_url=self.dcos_url,
            default_os_user=self.default_os_user,
            default_headers=self.default_headers,
            ca_cert_path=self.ca_cert_path,
            get_node_url=self.get_node_url)
        return marathon_client

    @property
    def metronome(self):
        return self.get_client('/service/metronome/v1')

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
