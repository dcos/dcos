#!/usr/bin/env python3
import logging
import time

import boto3
import retrying

from test_util.helpers import Host, retry_boto_rate_limits, SshInfo

LOGGING_FORMAT = '[%(asctime)s|%(name)s|%(levelname)s]: %(message)s'
logging.basicConfig(format=LOGGING_FORMAT, level=logging.DEBUG)
# AWS verbosity in debug mode overwhelms meaningful logging
logging.getLogger('botocore').setLevel(logging.INFO)
log = logging.getLogger(__name__)

VPC_TEMPLATE_URL = 'https://s3.amazonaws.com/vpc-cluster-template/vpc-cluster-template.json'
VPC_EBS_ONLY_TEMPLATE_URL = 'https://s3.amazonaws.com/vpc-cluster-template/vpc-ebs-only-cluster-template.json'


def template_by_instance_type(instance_type):
    if instance_type.split('.')[0] in ('c4', 't2', 'm4'):
        return VPC_EBS_ONLY_TEMPLATE_URL
    else:
        return VPC_TEMPLATE_URL


def instances_to_hosts(instances):
    return [Host(i.private_ip_address, i.public_ip_address) for i in instances]


class BotoWrapper():
    def __init__(self, region, aws_access_key_id, aws_secret_access_key):
        self.region = region
        self.session = boto3.session.Session(
            aws_access_key_id=aws_access_key_id, aws_secret_access_key=aws_secret_access_key)

    def client(self, name):
        return self.session.client(service_name=name, region_name=self.region)

    def resource(self, name):
        return self.session.resource(service_name=name, region_name=self.region)

    def create_key_pair(self, key_name):
        """Retruns private key of newly generated pair
        """
        key = self.resource('ec2').KeyPair(key_name)
        return key.key_material

    def delete_key_pair(self, key_name):
        self.resource('ec2').KeyPair(key_name).delete()

    def create_stack(self, name, template_url, user_parameters, deploy_timeout=60):
        """Returns boto stack object
        """
        log.info('Requesting AWS CloudFormation...')
        cf_parameters = []
        for k, v in user_parameters.items():
            cf_parameters.append({'ParameterKey': k, 'ParameterValue': v})
        self.resource('cloudformation').create_stack(
            StackName=name,
            TemplateURL=template_url,
            DisableRollback=True,
            TimeoutInMinutes=deploy_timeout,
            Capabilities=['CAPABILITY_IAM'],
            Parameters=cf_parameters)
        return CfStack(name, self)


class CfStack():
    def __init__(self, stack_name, boto_wrapper):
        self.boto_wrapper = boto_wrapper
        self.stack = self.boto_wrapper.resource('cloudformation').Stack(stack_name)
        self._host_cache = {}

    def wait_for_status_change(self, state_1, state_2, wait_before_poll_min, timeout=60 * 60):
        """
        Note: Do not use unwrapped boto waiter class, it has very poor error handling

        Stacks can have one of the following statuses. See:
        http://boto3.readthedocs.io/en/latest/reference/
        services/cloudformation.html#CloudFormation.Client.describe_stacks

        CREATE_IN_PROGRESS, CREATE_FAILED, CREATE_COMPLETE
        ROLLBACK_IN_PROGRESS, ROLLBACK_FAILED, ROLLBACK_COMPLETE
        DELETE_IN_PROGRESS, DELETE_FAILED, DELETE_COMPLETE
        UPDATE_IN_PROGRESS, UPDATE_COMPLETE_CLEANUP_IN_PROGRESS
        UPDATE_COMPLETE, UPDATE_ROLLBACK_IN_PROGRESS
        UPDATE_ROLLBACK_FAILED, UPDATE_ROLLBACK_COMPLETE
        UPDATE_ROLLBACK_COMPLETE_CLEANUP_IN_PROGRESS
        """
        log.info('Waiting for status to change from {} to {}'.format(state_1, state_2))
        log.info('Sleeping for {} minutes before polling'.format(wait_before_poll_min))
        time.sleep(60 * wait_before_poll_min)

        @retrying.retry(wait_fixed=10 * 1000,
                        stop_max_delay=timeout * 1000,
                        retry_on_result=lambda res: res is False,
                        retry_on_exception=lambda ex: False)
        def wait_loop():
            stack_details = self.get_stack_details()
            stack_status = stack_details['StackStatus']
            if stack_status == state_2:
                return True
            if stack_status != state_1:
                log.error('Stack Details: {}'.format(stack_details))
                for event in self.get_stack_events():
                    log.error('Stack Events: {}'.format(event))
                raise Exception('StackStatus changed unexpectedly to: {}'.format(stack_status))
            return False
        wait_loop()

    @retry_boto_rate_limits
    def get_stack_details(self):
        log.debug('Requesting stack details')
        return self.boto_wrapper.client('cloudformation').describe_stacks(
            StackName=self.stack.stack_id)['Stacks'][0]

    @retry_boto_rate_limits
    def get_stack_events(self):
        log.debug('Requesting stack events')
        return self.boto_wrapper.client('cloudformation').describe_stack_events(
            StackName=self.stack.stack_id)['StackEvents']

    def wait_for_stack_creation(self, wait_before_poll_min=3):
        self.wait_for_status_change('CREATE_IN_PROGRESS', 'CREATE_COMPLETE', wait_before_poll_min)

    def wait_for_stack_deletion(self, wait_before_poll_min=3):
        self.wait_for_status_change('DELETE_IN_PROGRESS', 'DELETE_COMPLETE', wait_before_poll_min)

    def get_parameter(self, param):
        """Returns param if in stack parameters, else returns None
        """
        for p in self.stack.parameters:
            if p['ParameterKey'] == param:
                return p['ParameterValue']
        raise KeyError('Key not found in template parameters: {}. Parameters: {}'.
                       format(param, self.stack.parameters))

    @retry_boto_rate_limits
    def get_auto_scaling_instances(self, logical_id):
        """ Get instances in ASG with logical_id. If logical_id is None, all ASGs will be used
        Will return instance objects as describd here:
        http://boto3.readthedocs.io/en/latest/reference/services/ec2.html#instance

        Note: there is no ASG resource hence the need for this method
        """
        ec2 = self.boto_wrapper.resource('ec2')
        return [ec2.Instance(i['InstanceId']) for asg in self.boto_wrapper.client('autoscaling').
                describe_auto_scaling_groups(
                    AutoScalingGroupNames=[self.stack.Resource(logical_id).physical_resource_id])
                ['AutoScalingGroups'] for i in asg['Instances']]

    def get_hosts_cached(self, group_name, refresh=False):
        if refresh or group_name not in self._host_cache:
            host_list = instances_to_hosts(self.get_auto_scaling_instances(group_name))
            self._host_cache[group_name] = host_list
            return host_list
        return self._host_cache[group_name]


class DcosCfSimple(CfStack):
    @classmethod
    def create(cls, stack_name, template_url, public_agents, private_agents,
               admin_location, key_pair_name, boto_wrapper):
        parameters = {
            'KeyName': key_pair_name,
            'AdminLocation': admin_location,
            'PublicSlaveInstanceCount': str(public_agents),
            'SlaveInstanceCount': str(private_agents)}
        stack = boto_wrapper.create_stack(stack_name, template_url, parameters)
        # Use stack_name as the binding identifier. At time of implementation,
        # stack.stack_name returns stack_id if Stack was created with ID
        return cls(stack.stack.stack_name, boto_wrapper), SSH_INFO['coreos']

    def delete(self):
        log.info('Starting deletion of CF stack')
        # boto stacks become unusable after deletion (e.g. status/info checks) if name-based
        self.stack = self.boto_wrapper.resource('cloudformation').Stack(self.stack.stack_id)
        self.stack.delete()
        self.empty_and_delete_s3_bucket_from_stack()

    def empty_and_delete_s3_bucket_from_stack(self):
        bucket_id = self.stack.Resource('ExhibitorS3Bucket').physical_resource_id
        s3 = self.boto_wrapper.resource('s3')
        bucket = s3.Bucket(bucket_id)
        log.info('Starting bucket {} deletion'.format(bucket))
        all_objects = bucket.objects.all()
        obj_count = len(list(all_objects))
        if obj_count > 0:
            assert obj_count == 1, 'Expected one object in Exhibitor S3 bucket but found: ' + str(obj_count)
            exhibitor_object = list(all_objects)[0]
            log.info('Trying to delete object from bucket: {}'.format(repr(exhibitor_object)))
            exhibitor_object.delete()
        log.info('Trying deleting bucket {} itself'.format(bucket))
        bucket.delete()
        log.info('Delete successfully triggered for {}'.format(self.stack.stack_name))

    def get_master_ips(self, refresh=False):
        return self.get_hosts_cached('MasterServerGroup', refresh=refresh)

    def get_public_agent_ips(self, refresh=False):
        return self.get_hosts_cached('PublicSlaveServerGroup', refresh=refresh)

    def get_private_agent_ips(self, refresh=False):
        return self.get_hosts_cached('SlaveServerGroup', refresh=refresh)


class DcosCfAdvanced(CfStack):
    @classmethod
    def create(cls, stack_name, boto_wrapper, template_url,
               public_agents, private_agents, key_pair_name,
               private_agent_type, public_agent_type, master_type,
               vpc_cidr='10.0.0.0/16', public_subnet_cidr='10.0.128.0/20',
               private_subnet_cidr='10.0.0.0/17',
               gateway=None, vpc=None, private_subnet=None, public_subnet=None):
        ec2 = boto_wrapper.client('ec2')
        if not vpc:
            log.info('Creating new VPC...')
            vpc = ec2.create_vpc(CidrBlock=vpc_cidr, InstanceTenancy='default')['Vpc']['VpcId']
            ec2.get_waiter('vpc_available').wait(VpcIds=[vpc])
            ec2.create_tags(Resources=[vpc], Tags=[{'Key': 'Name', 'Value': stack_name}])
        log.info('Using VPC with ID: ' + vpc)

        if not gateway:
            log.info('Creating new InternetGateway...')
            gateway = ec2.create_internet_gateway()['InternetGateway']['InternetGatewayId']
            ec2.attach_internet_gateway(InternetGatewayId=gateway, VpcId=vpc)
            ec2.create_tags(Resources=[gateway], Tags=[{'Key': 'Name', 'Value': stack_name}])
        log.info('Using InternetGateway with ID: ' + gateway)

        if not private_subnet:
            log.info('Creating new PrivateSubnet...')
            private_subnet = ec2.create_subnet(VpcId=vpc, CidrBlock=private_subnet_cidr)['Subnet']['SubnetId']
            ec2.create_tags(Resources=[private_subnet], Tags=[{'Key': 'Name', 'Value': stack_name + '-private'}])
            ec2.get_waiter('subnet_available').wait(SubnetIds=[private_subnet])
        log.info('Using PrivateSubnet with ID: ' + private_subnet)

        if not public_subnet:
            log.info('Creating new PublicSubnet...')
            public_subnet = ec2.create_subnet(VpcId=vpc, CidrBlock=public_subnet_cidr)['Subnet']['SubnetId']
            ec2.create_tags(Resources=[public_subnet], Tags=[{'Key': 'Name', 'Value': stack_name + '-public'}])
            ec2.get_waiter('subnet_available').wait(SubnetIds=[public_subnet])
        log.info('Using PublicSubnet with ID: ' + public_subnet)

        parameters = {
            'KeyName': key_pair_name,
            'Vpc': vpc,
            'InternetGateway': gateway,
            'MasterInstanceType': master_type,
            'PublicAgentInstanceCount': str(public_agents),
            'PublicAgentInstanceType': public_agent_type,
            'PublicSubnet': public_subnet,
            'PrivateAgentInstanceCount': str(private_agents),
            'PrivateAgentInstanceType': private_agent_type,
            'PrivateSubnet': private_subnet}
        stack = boto_wrapper.create_stack(stack_name, template_url, parameters)
        try:
            os_string = template_url.split('/')[-1].split('.')[-2].split('-')[0]
            ssh_info = CF_OS_SSH_INFO[os_string]
        except (KeyError, IndexError):
            log.exception('Unexpected template URL: {}'.format(template_url))
            if os_string:
                log.exception('No SSH info for OS string: {}'.format(os_string))
            raise
        return cls(stack.stack.stack_name, boto_wrapper), ssh_info

    def delete(self, delete_vpc=False):
        log.info('Starting deletion of CF Advanced stack')
        vpc_id = self.get_parameter('Vpc')
        # boto stacks become unusable after deletion (e.g. status/info checks) if name-based
        self.stack = self.boto_wrapper.resource('cloudformation').Stack(self.stack.stack_id)
        log.info('Deleting Infrastructure Stack')
        infrastack = DcosCfSimple(self.get_resource_stack('Infrastructure').stack.stack_id, self.boto_wrapper)
        infrastack.delete()
        log.info('Deleting Master Stack')
        self.get_resource_stack('MasterStack').stack.delete()
        log.info('Deleting Private Agent Stack')
        self.get_resource_stack('PrivateAgentStack').stack.delete()
        log.info('Deleting Public Agent Stack')
        self.get_resource_stack('PublicAgentStack').stack.delete()
        self.stack.delete()
        if delete_vpc:
            self.wait_for_stack_deletion()
            self.boto_wrapper.resource('ec2').Vpc(vpc_id).delete()

    def get_master_ips(self, refresh=False):
        return self.get_resource_stack('MasterStack').get_hosts_cached('MasterServerGroup', refresh=refresh)

    def get_private_agent_ips(self, refresh=False):
        return self.get_resource_stack('PrivateAgentStack').get_hosts_cached('PrivateAgentServerGroup', refresh=refresh)

    def get_public_agent_ips(self, refresh=False):
        return self.get_resource_stack('PublicAgentStack').get_hosts_cached('PublicAgentServerGroup', refresh=refresh)

    def get_resource_stack(self, resource_name):
        """Returns a CfStack for a given resource
        """
        return CfStack(self.stack.Resource(resource_name).physical_resource_id, self.boto_wrapper)


class VpcCfStack(CfStack):
    @classmethod
    def create(cls, stack_name, instance_type, instance_os, instance_count,
               admin_location, key_pair_name, boto_wrapper):
        ami_code = OS_AMIS[instance_os][boto_wrapper.region]
        template_url = template_by_instance_type(instance_type)
        parameters = {
            'KeyPair': key_pair_name,
            'AllowAccessFrom': admin_location,
            'ClusterSize': str(instance_count),
            'InstanceType': str(instance_type),
            'AmiCode': ami_code}
        stack = boto_wrapper.create_stack(stack_name, template_url, parameters)
        return cls(stack.stack.stack_name, boto_wrapper), OS_SSH_INFO[instance_os]

    def delete(self):
        # boto stacks become unusable after deletion (e.g. status/info checks) if name-based
        self.stack = self.boto_wrapper.resource('cloudformation').Stack(self.stack.stack_id)
        self.stack.delete()

    def get_vpc_host_ips(self):
        # the vpc templates use the misleading name CentOSServerAutoScale for all deployments
        # https://mesosphere.atlassian.net/browse/DCOS-11534
        return self.get_hosts_cached('CentOSServerAutoScale')


SSH_INFO = {
    'centos': SshInfo(
        user='centos',
        home_dir='/home/centos',
    ),
    'coreos': SshInfo(
        user='core',
        home_dir='/home/core',
    ),
    'debian': SshInfo(
        user='admin',
        home_dir='/home/admin',
    ),
    'rhel': SshInfo(
        user='ec2-user',
        home_dir='/home/ec2-user',
    ),
    'ubuntu': SshInfo(
        user='ubuntu',
        home_dir='/home/ubuntu',
    ),
}


OS_SSH_INFO = {
    'cent-os-7': SSH_INFO['centos'],
    'cent-os-7-dcos-prereqs': SSH_INFO['centos'],
    'coreos': SSH_INFO['coreos'],
    'debian-8': SSH_INFO['debian'],
    'rhel-7': SSH_INFO['rhel'],
    'ubuntu-16-04': SSH_INFO['ubuntu'],
}

CF_OS_SSH_INFO = {
    'el7': SSH_INFO['centos'],
    'coreos': SSH_INFO['coreos']
}


OS_AMIS = {
    'cent-os-7': {'ap-northeast-1': 'ami-965345f8',
                  'ap-southeast-1': 'ami-332de750',
                  'ap-southeast-2': 'ami-c80320ab',
                  'eu-central-1': 'ami-1548ae7a',
                  'eu-west-1': 'ami-2ea92f5d',
                  'sa-east-1': 'ami-2921ad45',
                  'us-east-1': 'ami-fa9b9390',
                  'us-west-1': 'ami-12b3ce72',
                  'us-west-2': 'ami-edf11b8d'},
    'cent-os-7-dcos-prereqs': {'ap-northeast-1': 'ami-965345f8',
                               'ap-southeast-1': 'ami-332de750',
                               'ap-southeast-2': 'ami-c80320ab',
                               'eu-central-1': 'ami-1548ae7a',
                               'eu-west-1': 'ami-2ea92f5d',
                               'sa-east-1': 'ami-2921ad45',
                               'us-east-1': 'ami-fa9b9390',
                               'us-west-1': 'ami-12b3ce72',
                               'us-west-2': 'ami-edf11b8d'},
    'coreos': {'ap-northeast-1': 'ami-84e0c7ea',
               'ap-southeast-1': 'ami-84e0c7ea',
               'ap-southeast-2': 'ami-f35b0590',
               'eu-central-1': 'ami-fdd4c791',
               'eu-west-1': 'ami-55d20b26',
               'sa-east-1': 'ami-f35b0590',
               'us-east-1': 'ami-37bdc15d',
               'us-west-1': 'ami-27553a47',
               'us-west-2': 'ami-00ebfc61'},
    'debian-8': {'ap-northeast-1': 'ami-fe54f3fe',
                 'ap-southeast-1': 'ami-60989c32',
                 'ap-southeast-2': 'ami-07e3993d',
                 'eu-central-1': 'ami-b092aaad',
                 'eu-west-1': 'ami-0ed89d79',
                 'sa-east-1': 'ami-a5bd3fb8',
                 'us-east-1': 'ami-8b9a63e0',
                 'us-west-1': 'ami-a5d621e1',
                 'us-west-2': 'ami-3d56520d'},
    'rhel-7': {'ap-northeast-1': 'ami-35556534',
               'ap-southeast-1': 'ami-941031c6',
               'ap-southeast-2': 'ami-83e08db9',
               'eu-central-1': 'ami-e25e6cff',
               'eu-west-1': 'ami-8cff51fb',
               'sa-east-1': 'ami-595ce844',
               'us-east-1': 'ami-a8d369c0',
               'us-west-1': 'ami-33cdd876',
               'us-west-2': 'ami-99bef1a9'},
    'ubuntu-16-04': {'ap-northeast-1': 'ami-0919cd68',
                     'ap-southeast-1': 'ami-42934921',
                     'ap-southeast-2': 'ami-623c0d01',
                     'eu-central-1': 'ami-a9a557c6',
                     'eu-west-1': 'ami-643d4217',
                     'sa-east-1': 'ami-60bd2d0c',
                     'us-east-1': 'ami-2ef48339',
                     'us-west-1': 'ami-a9a8e4c9',
                     'us-west-2': 'ami-746aba14'}
}
