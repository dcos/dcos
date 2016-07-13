import logging
import pkg_resources

from oauth2client.service_account import ServiceAccountCredentials
from googleapiclient import discovery
from retrying import retry

from test_util.installer_runner import Host

log = logging.getLogger(__name__)


def get_deployment_imports():
    imports = []
    for filename in ['centos7_cluster.jinja', 'centos7_cluster.jinja.schema']:
        imports.append({
            "content": pkg_resources.resource_string('test_util', 'gce/' + filename).decode(),
            "name": filename})

    return imports


# NOTE: this actually condenses a "launcher" and "cluster state" mechanism into one class. They should
# be two.
class GceVpc():
    def __init__(self, deployment, description, project, zone, credentials_filename):
        self.deployment = deployment
        self.description = description
        self.project = project
        self.zone = zone
        self.credentials = ServiceAccountCredentials.from_json_keyfile_name(
            credentials_filename,
            scopes='https://www.googleapis.com/auth/cloud-platform')
        self._compute = discovery.build('compute', 'v1', credentials=self.credentials)
        self._dm = discovery.build('deploymentmanager', 'v2', credentials=self.credentials)

    def get_state(self):
        return self._dm.deployments().get(project=self.project, deployment=self.deployment).execute()

    def launch(self, instance_count):
        deployment_api = self._dm.deployments()
        deployment_api.insert(
            project=self.project,
            body={
                'name': self.deployment,
                'description': self.description,
                'target': {
                    'imports': get_deployment_imports(),
                    'config': {
                        'content': pkg_resources.resource_string('test_util', 'gce/config.yaml').decode().format(
                            instance_count=instance_count)
                    }
                }
            }).execute()

    def delete(self):
        return self._dm.deployments().delete(project=self.project, deployment=self.deployment).execute()

    def wait_for_done(self):
        # Poll every 5 seconds
        @retry(wait_fixed=5000, retry_on_result=lambda x: x is False, retry_on_exception=lambda _: False)
        def poller():
            state = self.get_state()
            logging.info('Waiting for up. current status: %s, progress %s',
                         state['operation']['status'], state['operation']['progress'])
            return state['operation']['status'] == 'DONE'

        poller()

    def get_ips(self):
        resource_list = self._dm.resources().list(project=self.project, deployment=self.deployment).execute()

        # Get the instance group
        instance_group = None
        for resource in resource_list['resources']:
            if resource['type'] == 'compute.v1.instanceGroupManager':
                instance_group = resource
                break

        # Get the instance IPs
        instances = self._compute.instanceGroupManagers().listManagedInstances(
            project=self.project,
            zone=self.zone,
            instanceGroupManager=instance_group['name']).execute()

        hosts = []
        ci_api = self._compute.instances()
        for instance in instances['managedInstances']:
            # Because Google doesn't give direct access to the instance name from a managed group...
            name = instance['instance'].rsplit('/', 1)[1]
            instance = ci_api.get(project=self.project, zone=self.zone, instance=name).execute()
            assert len(instance['networkInterfaces']) == 1
            interface = instance['networkInterfaces'][0]
            internal_ip = interface['networkIP']
            assert len(interface['accessConfigs']) == 1
            external_ip = interface['accessConfigs'][0]['natIP']
            hosts.append(Host(internal_ip, external_ip))

        return hosts

    def hosts(self):
        return self.get_ips()


def make_vpc(unique_cluster_id, use_bare_os):
    assert use_bare_os is True, "use_bare_os True is the only supported option currently."

    log.info("Spinning up GCE VPC via Google Deployment Manager with ID: %s", unique_cluster_id)

    vpc = GceVpc(
        deployment=unique_cluster_id,
        description='VPC based Integration Test',
        project='inbound-bee-664',
        zone='us-central-1b',
        credentials_filename='gce-credentials.json')
    vpc.launch(5)  # 1 bootstrap, 1 master, 2 agents, 1 public agent

    return {
        'ssh_user': 'ops_shared',
        'ssh_key_path': 'ssh_key'
    }, vpc
