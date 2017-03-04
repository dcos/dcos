""" Abstractions for handling resources via Amazon Web Services (AWS) API

The intention of these utilities is to allow other infrastructure to
interact with AWS without having to understand AWS APIs. Additionally,
this module provides helper functions for the most common queries required
to manipulate and test a DC/OS cluster, which would be otherwise cumbersome
to do with AWS API calls only

BotoWrapper: AWS credentials and region bound to various helper methods
CfStack: Generic representation of a CloudFormation stack
DcosCfStack: Represents DC/OS in a simple deployment
DcosZenCfStack: Represents DC/OS  deployed from a zen template
MasterStack: thin wrapper for master stack in a zen template
PrivateAgentStack: thin wrapper for public agent stack in a zen template
PublicAgentStack: thin wrapper for public agent stack in a zen template
VpcCfStack: Represents a homogeneous cluster of hosts with a specific AMI
"""
import logging
import time

import boto3
import retrying
from botocore.exceptions import ClientError

from test_util.helpers import Host, retry_boto_rate_limits, SshInfo

log = logging.getLogger(__name__)

VPC_TEMPLATE_URL = 'https://s3.amazonaws.com/vpc-cluster-template/vpc-cluster-template.json'
VPC_EBS_ONLY_TEMPLATE_URL = 'https://s3.amazonaws.com/vpc-cluster-template/vpc-ebs-only-cluster-template.json'


def template_by_instance_type(instance_type):
    if instance_type.split('.')[0] in ('c4', 't2', 'm4'):
        return VPC_EBS_ONLY_TEMPLATE_URL
    else:
        return VPC_TEMPLATE_URL


def param_dict_to_aws_format(user_parameters):
    return [{'ParameterKey': k, 'ParameterValue': str(v)} for k, v in user_parameters.items()]


@retry_boto_rate_limits
def instances_to_hosts(instances):
    return [Host(i.private_ip_address, i.public_ip_address) for i in instances]


def fetch_stack(stack_name, boto_wrapper):
    log.debug('Attemping to fetch AWS Stack: {}'.format(stack_name))
    stack = boto_wrapper.resource('cloudformation').Stack(stack_name)
    for resource in stack.resource_summaries.all():
        if resource.logical_resource_id == 'MasterStack':
            log.debug('Using Zen DC/OS Cloudformation interface')
            return DcosZenCfStack(stack_name, boto_wrapper)
        if resource.logical_resource_id == 'MasterServerGroup':
            log.debug('Using Basic DC/OS Cloudformation interface')
            return DcosCfStack(stack_name, boto_wrapper)
    log.debug('Using VPC Cloudformation interface')
    return VpcCfStack(stack_name, boto_wrapper)


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
        """Returns private key of newly generated pair
        """
        log.info('Creating KeyPair: {}'.format(key_name))
        key = self.client('ec2').create_key_pair(KeyName=key_name)
        return key['KeyMaterial']

    def delete_key_pair(self, key_name):
        log.info('Deleting KeyPair: {}'.format(key_name))
        self.resource('ec2').KeyPair(key_name).delete()

    def create_stack(self, name, template_url, parameters, deploy_timeout=60):
        """Pulls template and checks user params versus temlate params.
        Does simple casting of strings or numbers
        Starts stack creation if validation is successful
        """
        log.info('Requesting AWS CloudFormation: {}'.format(name))
        return self.resource('cloudformation').create_stack(
            StackName=name,
            TemplateURL=template_url,
            DisableRollback=True,
            TimeoutInMinutes=deploy_timeout,
            Capabilities=['CAPABILITY_IAM'],
            # this python API only accepts data in string format; cast as string here
            # so that we may pass parameters directly from yaml (which parses numbers as non-strings)
            Parameters=[{str(k): str(v) for k, v in p.items()} for p in parameters])

    def create_vpc_tagged(self, cidr, name_tag):
        ec2 = self.client('ec2')
        log.info('Creating new VPC...')
        vpc_id = ec2.create_vpc(CidrBlock=cidr, InstanceTenancy='default')['Vpc']['VpcId']
        ec2.get_waiter('vpc_available').wait(VpcIds=[vpc_id])
        ec2.create_tags(Resources=[vpc_id], Tags=[{'Key': 'Name', 'Value': name_tag}])
        log.info('Created VPC with ID: {}'.format(vpc_id))
        return vpc_id

    def create_internet_gateway_tagged(self, vpc_id, name_tag):
        ec2 = self.client('ec2')
        log.info('Creating new InternetGateway...')
        gateway_id = ec2.create_internet_gateway()['InternetGateway']['InternetGatewayId']
        ec2.attach_internet_gateway(InternetGatewayId=gateway_id, VpcId=vpc_id)
        ec2.create_tags(Resources=[gateway_id], Tags=[{'Key': 'Name', 'Value': name_tag}])
        log.info('Created internet gateway with ID: {}'.format(gateway_id))
        return gateway_id

    def create_subnet_tagged(self, vpc_id, cidr, name_tag):
        ec2 = self.client('ec2')
        log.info('Creating new Subnet...')
        subnet_id = ec2.create_subnet(VpcId=vpc_id, CidrBlock=cidr)['Subnet']['SubnetId']
        ec2.create_tags(Resources=[subnet_id], Tags=[{'Key': 'Name', 'Value': name_tag}])
        ec2.get_waiter('subnet_available').wait(SubnetIds=[subnet_id])
        log.info('Created subnet with ID: {}'.format(subnet_id))
        return subnet_id

    def delete_subnet(self, subnet_id):
        log.info('Deleting subnet: {}'.format(subnet_id))
        self.client('ec2').delete_subnet(SubnetId=subnet_id)

    def delete_internet_gateway(self, gateway_id):
        ig = self.resource('ec2').InternetGateway(gateway_id)
        for vpc in ig.attachments:
            vpc_id = vpc['VpcId']
            log.info('Detaching gateway {} from vpc {}'.format(gateway_id, vpc_id))
            ig.detach_from_vpc(VpcId=vpc_id)
        log.info('Deleting internet gateway: {}'.format(gateway_id))
        ig.delete()

    def delete_vpc(self, vpc_id):
        log.info('Deleting vpc: {}'.format(vpc_id))
        self.client('ec2').delete_vpc(VpcId=vpc_id)

    @retry_boto_rate_limits
    def get_auto_scaling_instances(self, asg_physical_resource_id):
        """ Returns instance objects as described here:
        http://boto3.readthedocs.io/en/latest/reference/services/ec2.html#instance
        """
        ec2 = self.resource('ec2')
        return [ec2.Instance(i['InstanceId']) for asg in self.client('autoscaling').
                describe_auto_scaling_groups(
                    AutoScalingGroupNames=[asg_physical_resource_id])
                ['AutoScalingGroups'] for i in asg['Instances']]


class CfStack:
    def __init__(self, stack_name, boto_wrapper):
        self.boto_wrapper = boto_wrapper
        self.stack = self.boto_wrapper.resource('cloudformation').Stack(stack_name)

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
            log.info('Continuing to wait...')
            return False
        wait_loop()

    def wait_for_complete(self, wait_before_poll_min=0):
        status = self.get_stack_details()['StackStatus']
        if status.endswith('_COMPLETE'):
            return
        elif status.endswith('_IN_PROGRESS'):
            self.wait_for_status_change(
                status, status.replace('IN_PROGRESS', 'COMPLETE'),
                wait_before_poll_min)
        else:
            raise Exception('AWS Stack has entered unexpected state: {}'.format(status))

    @retry_boto_rate_limits
    def get_stack_details(self):
        details = self.boto_wrapper.client('cloudformation').describe_stacks(
            StackName=self.stack.stack_id)['Stacks'][0]
        log.debug('Stack details: {}'.format(details))
        return details

    @retry_boto_rate_limits
    def get_stack_events(self):
        log.debug('Requesting stack events')
        return self.boto_wrapper.client('cloudformation').describe_stack_events(
            StackName=self.stack.stack_id)['StackEvents']

    def get_parameter(self, param):
        """Returns param if in stack parameters, else returns None
        """
        for p in self.stack.parameters:
            if p['ParameterKey'] == param:
                return p['ParameterValue']
        raise KeyError('Key not found in template parameters: {}. Parameters: {}'.
                       format(param, self.stack.parameters))

    def delete(self):
        stack_id = self.stack.stack_id
        log.info('Deleting stack: {}'.format(stack_id))
        # boto stacks become unusable after deletion (e.g. status/info checks) if name-based
        self.stack = self.boto_wrapper.resource('cloudformation').Stack(stack_id)
        self.stack.delete()
        log.info('Delete successfully initiated for {}'.format(stack_id))


class CleanupS3BucketMixin:
    def delete_exhibitor_s3_bucket(self):
        """ A non-empty S3 bucket cannot be deleted, so check to
        see if it should be emptied first. If its non-empty, but
        has more than one item, error out as the bucket is perhaps
        not an exhibitor bucket and the user should be alerted
        """
        try:
            bucket = self.boto_wrapper.resource('s3').Bucket(
                self.stack.Resource('ExhibitorS3Bucket').physical_resource_id)
        except ClientError:
            log.exception('Bucket could not be fetched')
            log.warning('S3 bucket not found when expected during delete, moving on...')
            return
        log.info('Starting bucket {} deletion'.format(bucket))
        all_objects = list(bucket.objects.all())
        obj_count = len(all_objects)
        if obj_count == 1:
            all_objects[0].delete()
        elif obj_count > 1:
            raise Exception('Expected on item in Exhibitor S3 bucket but found: ' + obj_count)
        log.info('Trying deleting bucket {} itself'.format(bucket))
        bucket.delete()

    def delete(self):
        self.delete_exhibitor_s3_bucket()
        super().delete()


class DcosCfStack(CleanupS3BucketMixin, CfStack):
    """ This abstraction will work for a simple DC/OS template.
    A simple template has its exhibitor bucket and auto scaling groups
    for each of the master, public agent, and private agent groups
    """
    @classmethod
    def create(cls, stack_name: str, template_url: str, public_agents: int, private_agents: int,
               admin_location: str, key_pair_name: str, boto_wrapper: BotoWrapper):
        parameters = {
            'KeyName': key_pair_name,
            'AdminLocation': admin_location,
            'PublicSlaveInstanceCount': str(public_agents),
            'SlaveInstanceCount': str(private_agents)}
        stack = boto_wrapper.create_stack(stack_name, template_url, param_dict_to_aws_format(parameters))
        # Use stack_name as the binding identifier. At time of implementation,
        # stack.stack_name returns stack_id if Stack was created with ID
        return cls(stack.stack_id, boto_wrapper), SSH_INFO['coreos']

    @property
    def master_instances(self):
        yield from self.boto_wrapper.get_auto_scaling_instances(
            self.stack.Resource('MasterServerGroup').physical_resource_id)

    @property
    def private_agent_instances(self):
        yield from self.boto_wrapper.get_auto_scaling_instances(
            self.stack.Resource('SlaveServerGroup').physical_resource_id)

    @property
    def public_agent_instances(self):
        yield from self.boto_wrapper.get_auto_scaling_instances(
            self.stack.Resource('PublicSlaveServerGroup').physical_resource_id)

    def get_master_ips(self):
        return instances_to_hosts(self.master_instances)

    def get_private_agent_ips(self):
        return instances_to_hosts(self.private_agent_instances)

    def get_public_agent_ips(self):
        return instances_to_hosts(self.public_agent_instances)


class MasterStack(CleanupS3BucketMixin, CfStack):
    @property
    def instances(self):
        yield from self.boto_wrapper.get_auto_scaling_instances(
            self.stack.Resource('MasterServerGroup').physical_resource_id)


class PrivateAgentStack(CfStack):
    @property
    def instances(self):
        yield from self.boto_wrapper.get_auto_scaling_instances(
            self.stack.Resource('PrivateAgentServerGroup').physical_resource_id)


class PublicAgentStack(CfStack):
    @property
    def instances(self):
        yield from self.boto_wrapper.get_auto_scaling_instances(
            self.stack.Resource('PublicAgentServerGroup').physical_resource_id)


class DcosZenCfStack(CfStack):
    """Zen stacks are stacks that have the masters, infra, public agents, and private
    agents split into resources stacks under one zen stack
    """
    @classmethod
    def create(cls, stack_name, boto_wrapper, template_url,
               public_agents, private_agents, key_pair_name,
               private_agent_type, public_agent_type, master_type,
               gateway, vpc, private_subnet, public_subnet):
        parameters = {
            'KeyName': key_pair_name,
            'Vpc': vpc,
            'InternetGateway': gateway,
            'MasterInstanceType': master_type,
            'PublicAgentInstanceCount': public_agents,
            'PublicAgentInstanceType': public_agent_type,
            'PublicSubnet': public_subnet,
            'PrivateAgentInstanceCount': private_agents,
            'PrivateAgentInstanceType': private_agent_type,
            'PrivateSubnet': private_subnet}
        stack = boto_wrapper.create_stack(stack_name, template_url, param_dict_to_aws_format(parameters))
        os_string = None
        try:
            os_string = template_url.split('/')[-1].split('.')[-2].split('-')[0]
            ssh_info = CF_OS_SSH_INFO[os_string]
        except (KeyError, IndexError):
            log.critical('Unexpected template URL: {}'.format(template_url))
            if os_string is not None:
                log.critical('No SSH info for OS string: {}'.format(os_string))
            raise
        return cls(stack.stack_id, boto_wrapper), ssh_info

    @property
    def master_stack(self):
        return MasterStack(
            self.stack.Resource('MasterStack').physical_resource_id, self.boto_wrapper)

    @property
    def private_agent_stack(self):
        return PrivateAgentStack(
            self.stack.Resource('PrivateAgentStack').physical_resource_id, self.boto_wrapper)

    @property
    def public_agent_stack(self):
        return PublicAgentStack(
            self.stack.Resource('PublicAgentStack').physical_resource_id, self.boto_wrapper)

    @property
    def infrastructure(self):
        return CfStack(self.stack.Resource('Infrastructure').physical_resource_id, self.boto_wrapper)

    def delete(self):
        log.info('Starting deletion of Zen CF stack')
        # boto stacks become unusable after deletion (e.g. status/info checks) if name-based
        self.stack = self.boto_wrapper.resource('cloudformation').Stack(self.stack.stack_id)
        # These resources might have failed to create or been removed prior, except their
        # failures and log it out
        for s in [self.infrastructure, self.master_stack, self.private_agent_stack,
                  self.public_agent_stack]:
            try:
                s.delete()
            except:
                log.exception('Delete encountered an error!')
        super().delete()

    @property
    def master_instances(self):
        yield from self.master_stack.instances

    @property
    def private_agent_instances(self):
        yield from self.private_agent_stack.instances

    @property
    def public_agent_instances(self):
        yield from self.public_agent_stack.instances

    def get_master_ips(self):
        return instances_to_hosts(self.master_instances)

    def get_private_agent_ips(self):
        return instances_to_hosts(self.private_agent_instances)

    def get_public_agent_ips(self):
        return instances_to_hosts(self.public_agent_instances)


class VpcCfStack(CfStack):
    @classmethod
    def create(cls, stack_name, instance_type, instance_os, instance_count,
               admin_location, key_pair_name, boto_wrapper):
        ami_code = OS_AMIS[instance_os][boto_wrapper.region]
        template_url = template_by_instance_type(instance_type)
        parameters = {
            'KeyPair': key_pair_name,
            'AllowAccessFrom': admin_location,
            'ClusterSize': instance_count,
            'InstanceType': instance_type,
            'AmiCode': ami_code}
        stack = boto_wrapper.create_stack(stack_name, template_url, param_dict_to_aws_format(parameters))
        return cls(stack.stack_id, boto_wrapper), OS_SSH_INFO[instance_os]

    def delete(self):
        # boto stacks become unusable after deletion (e.g. status/info checks) if name-based
        self.stack = self.boto_wrapper.resource('cloudformation').Stack(self.stack.stack_id)
        self.stack.delete()

    @property
    def instances(self):
        # the vpc templates use the misleading name CentOSServerAutoScale for all deployments
        # https://mesosphere.atlassian.net/browse/DCOS-11534
        yield from self.boto_wrapper.get_auto_scaling_instances(
            self.stack.Resource('CentOSServerAutoScale').physical_resource_id)

    def get_host_ips(self):
        return instances_to_hosts(self.instances)


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
    'cent-os-7-dcos-prereqs': {'ap-northeast-1': 'ami-d93d69be',
                               'ap-southeast-1': 'ami-68da6a0b',
                               'ap-southeast-2': 'ami-21fefd42',
                               'eu-central-1': 'ami-e80bde87',
                               'eu-west-1': 'ami-68dcf20e',
                               'sa-east-1': 'ami-5c9cfa30',
                               'us-east-1': 'ami-b4f128a2',
                               'us-west-1': 'ami-d4b3edb4',
                               'us-west-2': 'ami-b863e1d8'},
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
