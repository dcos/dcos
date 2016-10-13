#!/usr/bin/env python3
import logging
import os
import time

import boto3
import retrying
from botocore.exceptions import ClientError

from test_util.helpers import Host, SshInfo

LOGGING_FORMAT = '[%(asctime)s|%(name)s|%(levelname)s]: %(message)s'
logging.basicConfig(format=LOGGING_FORMAT, level=logging.DEBUG)
logger = logging.getLogger(__name__)

VPC_TEMPLATE_URL = 'https://s3.amazonaws.com/vpc-cluster-template/vpc-cluster-template.json'
VPC_EBS_ONLY_TEMPLATE_URL = 'https://s3.amazonaws.com/vpc-cluster-template/vpc-ebs-only-cluster-template.json'

# At time of implementation, VPC averaged 4 minutes and CF 9 minutes
AWS_WAIT_BEFORE_POLL_MIN = os.getenv('AWS_WAIT_BEFORE_POLL_MIN', 3)


def template_by_instance_type(instance_type):
    if instance_type.split('.')[0] in ('c4', 't2', 'm4'):
        return VPC_EBS_ONLY_TEMPLATE_URL
    else:
        return VPC_TEMPLATE_URL


def instances_to_hosts(instances):
    return [Host(i['PrivateIpAddress'], i['PublicIpAddress'] if 'PublicIpAddress' in i else None) for i in instances]


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
        logging.info('Requesting AWS CloudFormation...')
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

    def wait_for_status_change(self, state_1, state_2, timeout=3600):
        """Note: Do not use boto waiter class, it has very poor error handling
        and will raise an exception when the rate limit is hit whereas botoclient
        methods will simply sleep and retry up to 4 times. After that a ClientError
        is raised, at which point the poll interval backs off
        """
        stack_states = [
            'CREATE_IN_PROGRESS', 'CREATE_FAILED', 'CREATE_COMPLETE',
            'ROLLBACK_IN_PROGRESS', 'ROLLBACK_FAILED', 'ROLLBACK_COMPLETE',
            'DELETE_IN_PROGRESS', 'DELETE_FAILED', 'DELETE_COMPLETE',
            'UPDATE_IN_PROGRESS', 'UPDATE_COMPLETE_CLEANUP_IN_PROGRESS',
            'UPDATE_COMPLETE', 'UPDATE_ROLLBACK_IN_PROGRESS',
            'UPDATE_ROLLBACK_FAILED', 'UPDATE_ROLLBACK_COMPLETE',
            'UPDATE_ROLLBACK_COMPLETE_CLEANUP_IN_PROGRESS']
        state_args = set([state_1, state_2])
        assert state_args.issubset(stack_states), 'Invalid state(s): {}. states must be one of: {}'.format(
            repr(state_args.difference(stack_states)), repr(stack_states))
        logging.info('Waiting for status to change from {} to {}'.format(state_1, state_2))

        logging.info('Sleeping for {} minutes before polling'.format(AWS_WAIT_BEFORE_POLL_MIN))
        time.sleep(60 * AWS_WAIT_BEFORE_POLL_MIN)
        default_poll_interval = 10

        @retrying.retry(stop_max_delay=timeout * 1000,
                        retry_on_result=lambda res: res is False,
                        retry_on_exception=lambda ex: False)
        def wait_and_backoff():
            nonlocal default_poll_interval
            try:
                self._wait_loop(state_1, state_2, default_poll_interval)
            except ClientError as e:
                if e.response['Error']['Code'] == 'Throttling':
                    logging.warn('AWS Client raised a throttling error; increasing poll interval...')
                    default_poll_interval += 10
                    return False
                raise
        wait_and_backoff()

    def _wait_loop(self, state_1, state_2, interval):
        """This method is still vulnerable to being interrupted by an
        AWS Client throttling error, use wait_for_status_change()
        """
        @retrying.retry(wait_fixed=interval * 1000,
                        retry_on_result=lambda res: res is False,
                        retry_on_exception=lambda ex: False)
        def wait_loop():
            stack_details = self.get_stack_details()
            stack_status = stack_details['StackStatus']
            if stack_status == state_2:
                return True
            if stack_status != state_1:
                logging.exception('Stack Details: {}'.format(stack_details))
                for event in self.get_stack_events():
                    logging.exception('Stack Events: {}'.format(repr(event)))
                raise Exception('StackStatus changed unexpectedly to: {}'.format(stack_status))
            return False
        wait_loop()

    def get_stack_details(self):
        return self.boto_wrapper.client('cloudformation').describe_stacks(
            StackName=self.stack.stack_id)['Stacks'][0]

    def get_stack_events(self):
        return self.boto_wrapper.client('cloudformation').describe_stack_events(
            StackName=self.stack.stack_id)['StackEvents']

    def wait_for_stack_creation(self):
        self.wait_for_status_change('CREATE_IN_PROGRESS', 'CREATE_COMPLETE')

    def wait_for_stack_deletion(self):
        self.wait_for_status_change('DELETE_IN_PROGRESS', 'DELETE_COMPLETE')


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
        logger.info('Starting deletion of CF stack')
        # boto stacks become unusable after deletion (e.g. status/info checks) if name-based
        self.stack = self.boto_wrapper.resource('cloudformation').Stack(self.stack.stack_id)
        self.stack.delete()
        self.empty_and_delete_s3_bucket_from_stack()

    def empty_and_delete_s3_bucket_from_stack(self):
        bucket_id = self.stack.Resource('ExhibitorS3Bucket').physical_resource_id
        s3 = self.boto_wrapper.resource('s3')
        bucket = s3.Bucket(bucket_id)
        logger.info('Starting bucket {} deletion'.format(bucket))
        all_objects = bucket.objects.all()
        obj_count = len(list(all_objects))
        if obj_count > 0:
            assert obj_count == 1, 'Expected one object in Exhibitor S3 bucket but found: ' + str(obj_count)
            exhibitor_object = list(all_objects)[0]
            logger.info('Trying to delete object from bucket: {}'.format(repr(exhibitor_object)))
            exhibitor_object.delete()
        logger.info('Trying deleting bucket {} itself'.format(bucket))
        bucket.delete()
        logger.info('Delete successfully triggered for {}'.format(self.stack.stack_name))

    def get_master_ips(self, state_list=None):
        instances = self.get_group_instances(['MasterServerGroup'], state_list)
        return instances_to_hosts(instances)

    def get_public_agent_ips(self, state_list=None):
        instances = self.get_group_instances(['PublicSlaveServerGroup'], state_list)
        return instances_to_hosts(instances)

    def get_private_agent_ips(self, state_list=None):
        instances = self.get_group_instances(['SlaveServerGroup'], state_list)
        return instances_to_hosts(instances)

    def get_group_instances(self, group_list, state_list=None):
        """Returns a list of dictionaries that describe currently running instances of group
        """
        filters = [{'Name': 'tag:aws:cloudformation:stack-name', 'Values': [self.stack.stack_name]}]
        if group_list:
            filters.append({'Name': 'tag:aws:cloudformation:logical-id', 'Values': group_list})
        if state_list:
            filters.append({'Name': 'instance-state-name', 'Values': state_list})
        reservations = self.boto_wrapper.client('ec2').describe_instances(
            Filters=filters)['Reservations']
        return [instance for res in reservations for instance in res['Instances']]


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
            logging.info('Creating new VPC...')
            vpc = ec2.create_vpc(CidrBlock=vpc_cidr, InstanceTenancy='default')['Vpc']['VpcId']
            ec2.get_waiter('vpc_available').wait(VpcIds=[vpc])
            ec2.create_tags(Resources=[vpc], Tags=[{'Key': 'Name', 'Value': stack_name}])
        logging.info('Using VPC with ID: ' + vpc)

        if not gateway:
            logging.info('Creating new InternetGateway...')
            gateway = ec2.create_internet_gateway()['InternetGateway']['InternetGatewayId']
            ec2.attach_internet_gateway(InternetGatewayId=gateway, VpcId=vpc)
            ec2.create_tags(Resources=[gateway], Tags=[{'Key': 'Name', 'Value': stack_name}])
        logging.info('Using InternetGateway with ID: ' + gateway)

        if not private_subnet:
            logging.info('Creating new PrivateSubnet...')
            private_subnet = ec2.create_subnet(VpcId=vpc, CidrBlock=private_subnet_cidr)['Subnet']['SubnetId']
            ec2.create_tags(Resources=[private_subnet], Tags=[{'Key': 'Name', 'Value': stack_name + '-private'}])
            ec2.get_waiter('subnet_available').wait(SubnetIds=[private_subnet])
        logging.info('Using PrivateSubnet with ID: ' + private_subnet)

        if not public_subnet:
            logging.info('Creating new PublicSubnet...')
            public_subnet = ec2.create_subnet(VpcId=vpc, CidrBlock=public_subnet_cidr)['Subnet']['SubnetId']
            ec2.create_tags(Resources=[public_subnet], Tags=[{'Key': 'Name', 'Value': stack_name + '-public'}])
            ec2.get_waiter('subnet_available').wait(SubnetIds=[public_subnet])
        logging.info('Using PublicSubnet with ID: ' + public_subnet)

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
            logging.exception('Unexpected template URL: {}'.format(template_url))
            if os_string:
                logging.exception('No SSH info for OS string: {}'.format(os_string))
            raise
        return cls(stack.stack.stack_name, boto_wrapper), ssh_info

    def delete(self, delete_vpc=False):
        logger.info('Starting deletion of CF Advanced stack')
        # Get VPC id first
        for p in self.stack.parameters:
            if p['ParameterKey'] == 'Vpc':
                vpc_id = p['ParameterValue']
                break
        # boto stacks become unusable after deletion (e.g. status/info checks) if name-based
        self.stack = self.boto_wrapper.resource('cloudformation').Stack(self.stack.stack_id)
        logging.info('Deleting Infrastructure Stack')
        infrastack = DcosCfSimple(self.get_resource_stack('Infrastructure').stack.stack_id, self.boto_wrapper)
        infrastack.delete()
        logging.info('Deleting Master Stack')
        self.get_resource_stack('MasterStack').stack.delete()
        logging.info('Deleting Private Agent Stack')
        self.get_resource_stack('PrivateAgentStack').stack.delete()
        logging.info('Deleting Public Agent Stack')
        self.get_resource_stack('PublicAgentStack').stack.delete()
        self.stack.delete()
        if delete_vpc:
            self.wait_for_stack_deletion()
            self.boto_wrapper.resource('ec2').Vpc(vpc_id).delete()

    def get_vpc(self):
        vpc_id = self.boto_wrapper.client('ec2').describe_vpcs(Filters=[
            {'Name': 'tag:Name', 'Values': [self.stack.stack_name]}])['Vpcs'][0]['VpcId']
        return self.boto_wrapper.resouce('ec2').Vpc(vpc_id)

    def get_master_ips(self):
        return self.get_substack_hosts('MasterStack')

    def get_private_agent_ips(self):
        return self.get_substack_hosts('PrivateAgentStack')

    def get_public_agent_ips(self):
        return self.get_substack_hosts('PublicAgentStack')

    def get_resource_stack(self, resource_name):
        """Returns a CfStack for a given resource
        """
        resources = self.boto_wrapper.client('cloudformation').describe_stack_resources(StackName=self.stack.stack_name)
        print(resources)
        for r in resources['StackResources']:
            if r['LogicalResourceId'] == resource_name:
                return CfStack(r['PhysicalResourceId'], self.boto_wrapper)

    def get_substack_instance_ids(self, substack):
        """returns list of instance ids
        """
        asg = self.get_resource_stack(substack).stack.\
            Resource(substack.replace('Stack', 'ServerGroup')).physical_resource_id
        return [i['InstanceId'] for i in self.boto_wrapper.client('autoscaling').
                describe_auto_scaling_groups(
                AutoScalingGroupNames=[asg])['AutoScalingGroups'][0]['Instances']]

    def get_substack_hosts(self, substack):
        instances = self.boto_wrapper.client('ec2').describe_instances(
            InstanceIds=self.get_substack_instance_ids(substack))['Reservations'][0]['Instances']
        return instances_to_hosts(instances)


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
        reservations = self.boto_wrapper.client('ec2').describe_instances(Filters=[{
            'Name': 'tag-value', 'Values': [self.stack.stack_name]}])['Reservations']
        logging.debug('Reservations for {}: {}'.format(self.stack.stack_id, reservations))
        instances = reservations[0]['Instances']
        return instances_to_hosts(instances)


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
