#!/usr/bin/env python3
import logging
from collections import namedtuple

import boto3

LOGGING_FORMAT = '[%(asctime)s|%(name)s|%(levelname)s]: %(message)s'
logging.basicConfig(format=LOGGING_FORMAT, level=logging.DEBUG)
logger = logging.getLogger(__name__)

Host = namedtuple('Host', ['private_ip', 'public_ip'])

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
        return cls(stack.stack.stack_id, boto_wrapper)

    def delete(self):
        logger.info('Starting deletion of CF stack')
        # boto stacks become unusable after deletion (e.g. status/info checks) if name-based
        self.stack = self.boto_wrapper.resource('cloudformation').Stack(self.stack.stack_id)
        self.stack.delete()
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
                'AmiCode': ami_code
                }
        stack = boto_wrapper.create_stack(stack_name, template_url, parameters)
        return cls(stack.stack.stack_id, boto_wrapper)

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


OS_AMIS = {
    'cent-os-6': {'ap-northeast-1': 'ami-82640282',
                  'ap-southeast-1': 'ami-44617116',
                  'ap-southeast-2': 'ami-7b81ca41',
                  'eu-central-1': 'ami-2a868b37',
                  'eu-west-1': 'ami-2b7f4c5c',
                  'sa-east-1': 'ami-fd0f99e0',
                  'us-east-1': 'ami-57cd8732',
                  'us-west-1': 'ami-45844401',
                  'us-west-2': 'ami-1255b321'},
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
    'rhel-6': {'ap-northeast-1': 'ami-78379d78',
               'ap-southeast-1': 'ami-faedeea8',
               'ap-southeast-2': 'ami-7f0d4b45',
               'eu-central-1': 'ami-8e96ac93',
               'eu-west-1': 'ami-78d29c0f',
               'sa-east-1': 'ami-d1d35ccc',
               'us-east-1': 'ami-0d28fe66',
               'us-west-1': 'ami-5b8a781f',
               'us-west-2': 'ami-75f3f145'},
    'rhel-7': {'ap-northeast-1': 'ami-35556534',
               'ap-southeast-1': 'ami-941031c6',
               'ap-southeast-2': 'ami-83e08db9',
               'eu-central-1': 'ami-e25e6cff',
               'eu-west-1': 'ami-8cff51fb',
               'sa-east-1': 'ami-595ce844',
               'us-east-1': 'ami-a8d369c0',
               'us-west-1': 'ami-33cdd876',
               'us-west-2': 'ami-99bef1a9'},
    'ubuntu-12-04': {'ap-northeast-1': 'ami-88bca789',
                     'ap-southeast-1': 'ami-74c6ec26',
                     'ap-southeast-2': 'ami-33d4a009',
                     'eu-central-1': 'ami-9cc4f681',
                     'eu-west-1': 'ami-ff810f88',
                     'sa-east-1': 'ami-57f14e4a',
                     'us-east-1': 'ami-427a392a',
                     'us-west-1': 'ami-82bba3c7',
                     'us-west-2': 'ami-2b471c1b'},
    'ubuntu-14-04': {'ap-northeast-1': 'ami-936d9d93',
                     'ap-southeast-1': 'ami-96f1c1c4',
                     'ap-southeast-2': 'ami-69631053',
                     'eu-central-1': 'ami-accff2b1',
                     'eu-west-1': 'ami-47a23a30',
                     'sa-east-1': 'ami-4d883350',
                     'us-east-1': 'ami-d05e75b8',
                     'us-west-1': 'ami-df6a8b9b',
                     'us-west-2': 'ami-5189a661'}
}
