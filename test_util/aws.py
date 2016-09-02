#!/usr/bin/env python3
import logging
from collections import namedtuple

import boto3

LOGGING_FORMAT = '[%(asctime)s|%(name)s|%(levelname)s]: %(message)s'
logging.basicConfig(format=LOGGING_FORMAT, level=logging.DEBUG)
logger = logging.getLogger(__name__)

Host = namedtuple('Host', ['private_ip', 'public_ip'])
SshInfo = namedtuple('SshInfo', ['user', 'home_dir'])

VPC_TEMPLATE_URL = 'https://s3.amazonaws.com/vpc-cluster-template/vpc-cluster-template.json'
VPC_EBS_ONLY_TEMPLATE_URL = 'https://s3.amazonaws.com/vpc-cluster-template/vpc-ebs-only-cluster-template.json'


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

    def wait_for_stack_creation(self):
        self.boto_wrapper.client('cloudformation').get_waiter('stack_create_complete').\
            wait(StackName=self.stack.stack_name)

    def wait_for_stack_deletion(self):
        self.boto_wrapper.client('cloudformation').get_waiter('stack_delete_complete').\
            wait(StackName=self.stack.stack_name)


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
        return cls(stack.stack.stack_id, boto_wrapper), SSH_INFO['coreos']

    def delete(self):
        logger.info('Starting deletion of CF stack')
        # boto stacks become unusable after deletion (e.g. status/info checks) if name-based
        self.stack = self.boto_wrapper.resource('cloudformation').Stack(self.stack.stack_id)
        self.stack.delete()
        self.empty_and_delete_s3_bucket_from_stack()

    def get_tag_instances(self, tag):
        return self.boto_wrapper.client('ec2').describe_instances(
            Filters=[
                {'Name': 'tag-value', 'Values': [self.stack.stack_name]},
                {'Name': 'tag-value', 'Values': [tag]}])['Reservations'][0]['Instances']

    def get_master_ips(self):
        instances = self.get_tag_instances('MasterServerGroup')
        return instances_to_hosts(instances)

    def get_public_agent_ips(self):
        instances = self.get_tag_instances('PublicSlaveServerGroup')
        return instances_to_hosts(instances)

    def get_private_agent_ips(self):
        instances = self.get_tag_instances('SlaveServerGroup')
        return instances_to_hosts(instances)

    def empty_and_delete_s3_bucket_from_stack(self):
        bucket_id = self.stack.Resource('ExhibitorS3Bucket').physical_resource_id
        s3 = self.boto_wrapper.resource('s3')
        bucket = s3.Bucket(bucket_id)
        logger.info('Starting bucket {} deletion'.format(bucket))
        all_objects = bucket.objects.all()
        obj_count = len(list(all_objects))
        if obj_count > 0:
            assert obj_count == 1, 'Expected one object in Exhibitor S3 bucket but found: ' + str(obj_count)
            logger.info('Trying to delete object from bucket: {}'.format(repr(all_objects[0])))
            all_objects[0].delete()
        logger.info('Trying deleting bucket {} itself'.format(bucket))
        bucket.delete()
        logger.info('Delete successfully triggered for {}'.format(self.stack.stack_name))


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
        return cls(stack.stack.stack_id, boto_wrapper), SSH_INFO['coreos']

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
        return cls(stack.stack.stack_id, boto_wrapper), OS_SSH_INFO[instance_os]

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
