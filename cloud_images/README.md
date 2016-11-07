# CentOS 7

## Create CentOS 7 base AMI

Steps to create a base CentOS 7 AMI which does not have any marketplace codes attached. This is necessary because any images derived from a Marketplace image cannot be shared publicly.

1. In the dcos.io AWS account, launch latest [CentOS 7 Marketplace AMI](https://wiki.centos.org/Cloud/AWS) with secondary 8GB EBS volume attached
2. Copy `centos7/create_base_ami.sh` to the launched instance and run the script with DEVICE set to secondary EBS volume (e.g. /dev/xvdf)
3. Detach secondary EBS volume
4. Create snapshot of EBS volume with name: centos7-YYYYMMDDhhmm
5. Create AMI from snapshot
   Name: centos7-YYYYMMDDhhmm (use same value as snapshot)
   Virtualization type: Hardware-assisted virtualization
   Volume Type: GP2
   Everything else: defaults
6. Update AMI Permissions to 'Public'
6. Record in CHANGELOG new AMI details

## Create DC/OS ready CentOS 7 AMI

Steps to create a new AMI with the DC/OS pre-requisites installed using a base CentOS 7 AMI (Marketplace or otherwise) and [Packer](https://www.packer.io/).

1. Change the working directory to the `centos7` subdirectory
2. Run the helper script `create_dcos_ami.sh` to build and deploy new DC/OS AMI's. Default values can be overridden by setting the appropriate environment variables.

# Reference Material

[Guidelines for Shared Linux AMIs](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/building-shared-amis.html)

# Notes
1. Use `date +"%Y%m%d%H%M"` to get the name for the snapshot and ami
2. m3.xlarge is not available in all regions, use the latest equivalent when building new regions
