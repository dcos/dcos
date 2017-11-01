# Building base and DC/OS-ready AMIs

This example references `centos7`; other platforms (eg. `rhel7`) can be substituted.

## Create base AMI

Steps to create a base AMI:

1. Create an AMI from the latest marketplace image with a secondary 8gb EBS volume attached. Export the public hostname of your launched AMI to `${HOST}`:
```
$ export HOST=ec2-34-208-126-68.us-west-2.compute.amazonaws.com
```

2. Copy the `centos7` folder to `${HOST}`, then connect via SSH:
```
$ scp -r centos7 centos@${HOST}:.
$ ssh centos@${HOST}
```

The following steps are performed on the launched AMI:

3. `cd` into the `centos7` folder and run `create_base_ami.sh` specifying the secondary EBS volume's raw device:
```
[centos@ip-172-31-45-48 ]$ cd centos7/
[centos@ip-172-31-45-48 centos7]$ sudo DEVICE=/dev/xvdb sh create_base_ami.sh
```

4. Detach secondary EBS volume
5. Create snapshot of EBS volume with name: `centos7-YYYYMMDDhhmm`
6. Create AMI from snapshot

   Name: `centos7-YYYYMMDDhhmm` (use same value as snapshot),
   Virtualization type: `Hardware-assisted virtualization`
7. Update AMI Permissions to 'Public'
8. Record in `CHANGELOG.md` new AMI details

## Create DC/OS-ready AMI

The following steps will create a new AMI with the DC/OS pre-requisites installed via [Packer](https://www.packer.io/):

1. Change the working directory to the `centos7` subdirectory
2. Run the helper script `create_dcos_ami.sh` to build and deploy new DC/OS AMI's. Default values can be overridden by setting the appropriate environment variables

# Reference Material

[Guidelines for Shared Linux AMIs](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/building-shared-amis.html)

