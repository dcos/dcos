## Changelog

### 2018-03-12

#### dcos-centos7-201803121129

* Adding support for fifth generation EC2 instances (i.e. m5 and c5):
* Support for AWS ENA network adapters.
* Enhancing DC/OS volume setup script to work with different block device names.

Base (source) AMI:
* ami-bd48b3c0 (us-east-1)

DC/OS AMI's:
ap-northeast-1: ami-f1aee697
ap-northeast-2: ami-74a8041a
ap-south-1: ami-866e37e9
ap-southeast-1: ami-a55504d9
ap-southeast-2: ami-5ba66539
ca-central-1: ami-8478ffe0
eu-central-1: ami-6a610905
eu-west-1: ami-c51a54bc
eu-west-2: ami-891ef9ee
eu-west-3: ami-c55fe9b8
sa-east-1: ami-f8f2b894
us-east-1: ami-27e5235a
us-east-2: ami-8f0234ea
us-west-1: ami-03bbae63
us-west-2: ami-845acbfc

### 2017-10-20

#### cloud_images

Support for building on Red Hat Linux
* new `rhel7/` folder/image and build scripts
* added `lib` folder with shared provisioning scripts
* reworked `centos7/` scripts to use shared provisioning scripts
* updated `README.md` to be more platform-agnostic

### 2017-05-29

#### dcos-centos7-201705292021

Base (source) AMI:
* ami-31a8ca51

DC/OS AMI's:
* ap-northeast-1: ami-1d50567a
* ap-northeast-2: ami-25da064b
* ap-south-1: ami-87601ce8
* ap-southeast-1: ami-f4a12097
* ap-southeast-2: ami-0d50476e
* ca-central-1: ami-3b3f835f
* eu-central-1: ami-d47fa4bb
* eu-west-1: ami-b6c8ded0
* eu-west-2: ami-c0dfc8a4
* sa-east-1: ami-41640d2d
* us-east-1: ami-5f5d1449
* us-east-2: ami-2e5c7a4b
* us-west-1: ami-54614234
* us-west-2: ami-61acce01

#### dcos-centos7-201705292024

Base (source) AMI:
* ami-36b43357

DC/OS AMI's:
* us-gov-west-1: ami-35b43354

### 2017-03-07

#### dcos-centos7-201703071551

Base (source) AMI:
* ami-c5af54a5

DC/OS AMI's:
* ap-northeast-1: ami-5942133e
* ap-northeast-2: ami-0d69b963
* ap-south-1: ami-47473728
* ap-southeast-1: ami-83ea59e0
* ap-southeast-2: ami-7f393b1c
* ca-central-1: ami-5359e437
* eu-central-1: ami-9e13c7f1
* eu-west-1: ami-41b89327
* eu-west-2: ami-60ecf904
* sa-east-1: ami-6d600101
* us-east-1: ami-84862092
* us-east-2: ami-fd6c4898
* us-west-1: ami-794f1619
* us-west-2: ami-4953df29

#### dcos-centos7-201703071626

Base (source) AMI:
* ami-7dff411c

DC/OS AMI's:
* us-gov-west-1: ami-8dce4bec

### 2016-08-30

* Fix intermittent issue with Docker 1.11.2 startup where a small percentage of agents (~5%) fail to start.

### 2016-08-09

Move AMI builds to dcos.io CI: https://teamcity.mesosphere.io/project.html?projectId=DcosIo_Dcos_BuildCloudBaseImages&tab=projectOverview

### 2016-06-07

#### centos7-201606080106

Base (source) AMI:
* ami-c5af54a5

DC/OS AMI's:
* ap-northeast-1: ami-b8d831d9
* ap-southeast-1: ami-133eee70
* ap-southeast-2: ami-f57d5496
* eu-central-1: ami-2e6f8141
* eu-west-1: ami-20af3253
* sa-east-1: ami-89179ce5
* us-east-1: ami-7848b115
* us-west-1: ami-a891ebc8
* us-west-2: ami-1e22d97e

#### centos7-201606081536

Base (source) AMI:
* ami-7dff411c

DC/OS AMI's:
* us-gov-west-1: ami-4e02bd2f

#### centos7-201709062029

Base (source) AMI:
* ami-6eed1a16

DC/OS AMI's:
* ap-northeast-1:ami-e21fd884
* ap-northeast-2:ami-94a378fa
* ap-south-1:ami-59276036
* ap-southeast-1:ami-3b8ee058
* ap-southeast-2:ami-c2e501a0
* ca-central-1:ami-3801bf5c
* eu-central-1:ami-868531e9
* eu-west-1:ami-5f03c426
* eu-west-2:ami-0da4b469
* sa-east-1:ami-5d2f5d31
* us-east-1:ami-abb1a2d0
* us-east-2:ami-807d5fe5
* us-west-1:ami-f6427596
* us-west-2:ami-6eed1a16

#### dcos-centos7-201709062024

Base (source) AMI:
* ami-e58c0f84

DC/OS AMI's:
* us-gov-west-1: ami-e58c0f84

#### dcos-centos7-201709252313

Update to CentOS 7.4.1708

Base (source) AMI from centos:
* ami-a9b24bd1

DC/OS AMIs (with prereqs)

* ap-northeast-1:ami-72f93314
* ap-northeast-2:ami-94b369fa
* ap-south-1:ami-ac1455c3
* ap-southeast-1:ami-cac2b2a9
* ap-southeast-2:ami-a0d736c2
* ca-central-1:ami-7d7ac319
* eu-central-1:ami-b371c1dc
* eu-west-1:ami-4d4f8634
* eu-west-2:ami-0b889b6f
* sa-east-1:ami-1264187e
* us-east-1:ami-b05aadca
* us-east-2:ami-08765b6d
* us-west-1:ami-63cafb03
* us-west-2:ami-1de01e65

#### centos7-201709262005

Update to CentOS 7.4.1708 (no DC/OS prereqs)

* ap-northeast-1: ami-965345f8
* ap-southeast-1: ami-8af586e9
* ap-southeast-2: ami-427d9c20
* eu-central-1: ami-2d0cbc42
* eu-west-1: ami-e46ea69d
* sa-east-1: ami-a5acd0c9
* us-east-1: ami-771beb0d
* us-west-1: ami-866151e6
* us-west-2: ami-a9b24bd1

#### dcos-centos7-201710122205

Update GovCloud CentOS AMI to 7.4

DC/OS AMIs (with prereqs)

* us-gov-west-1: ami-9923a1f8

