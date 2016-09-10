#!/usr/bin/env python3
import logging
from collections import namedtuple

import boto3

LOGGING_FORMAT = '[%(asctime)s|%(name)s|%(levelname)s]: %(message)s'
logging.basicConfig(format=LOGGING_FORMAT, level=logging.DEBUG)
logger = logging.getLogger(__name__)

Host = namedtuple('Host', ['private_ip', 'public_ip'])


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
        # Only covers if stack is created, instances might not be running
        self.boto_wrapper.client('cloudformation').get_waiter('stack_create_complete').\
            wait(StackName=self.stack.stack_name)

    def wait_for_stack_deletion(self):
        self.boto_wrapper.client('cloudformation').get_waiter('stack_delete_complete').\
            wait(StackName=self.stack.stack_name)

    def get_instance_from_private_ip(self, ip):
        "Returns the instance boto object associated with the private-ip given"
        instance_info = self.boto_wrapper.client('ec2').describe_instances(
            Filters=[
                {'Name': 'private-ip-address', 'Values': [ip]},
                {'Name': 'tag:aws:cloudformation:stack-name', 'Values': [self.stack.stack_name]},
                {'Name': 'instance-state-name', 'Values': ['running']}])['Reservations'][0]['Instances']
        assert len(instance_info) == 1, 'Expected only one instance running with private IP {}, '\
            'but found multiple: {}'.format(ip, repr(instance_info))
        return self.boto_wrapper.resource('ec2').Instance(instance_info[0]['InstanceId'])

    def set_autoscaling_group_capacity(self, target, count):
        asg_client = self.boto_wrapper.client('autoscaling')
        group_info = asg_client.describe_auto_scaling_groups()
        asg_name = None
        for group in group_info['AutoScalingGroups']:
            for tag in group['Tags']:
                if tag['Key'] == 'aws:cloudformation:stack-name' and tag['Value'] != self.stack.stack_name:
                    continue
                if tag['Key'] == 'aws:cloudformation:logical-id' and tag['Value'] == target:
                    asg_name = group['AutoScalingGroupName']
        if not asg_name:
            raise KeyError('Autoscaling Group {} not found'.format(target))
        asg_client.set_desired_capacity(AutoScalingGroupName=asg_name, DesiredCapacity=count)


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

    def get_master_ips(self):
        instances = self.get_group_instances(['MasterServerGroup'])
        return instances_to_hosts(instances)

    def get_public_agent_ips(self):
        instances = self.get_group_instances(['PublicSlaveServerGroup'])
        return instances_to_hosts(instances)

    def get_private_agent_ips(self):
        instances = self.get_group_instances(['SlaveServerGroup'])
        return instances_to_hosts(instances)

    def get_group_instances(self, group_list, state_list=['running']):
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
