# DC/OS on windows

DC/OS on Windows is a **work in progress**. As such there is **no guarantee it works**.  It is not currently complete. This document covers where the project is and what is planned for the near future.

## The high-level goal of DC/OS on Windows

Allow a full DC/OS installation as it is on Linux today, but with the addition of public and private Windows agents.
Once installed, jobs can be pushed to either Linux or Windows agent, using necessary constraints as generally things that work on one of these platforms is unlikely to work on the other. Constraints today include things like the node being public or private, but with windows additions that will need to be a part of the constraints also.
There are currently no plans to make the masters run on Windows.

## How to install

As of the writing of this document, the only way of installing DC/OS is using [acs-engine](https://github.com/Azure/acs-engine/blob/master/docs/dcos.md). This document only talks about Linux, although [this acs-engine .json configuration file](https://github.com/Azure/acs-engine/blob/master/examples/windows/dcos-winagent.json) does show an example of configuration for 1 master and 2 windows agents. Once installed, specifying a service constraint of `os=windows` would allow a service to be sent to a windows agent.

This installation approach allows you to deploy a specific version of DC/OS in an Azure environment with a set of masters, and a set of public and private Linux/Windows agents. The Windows agents are installed from a *last known good* version of the windows binaries.

The goal is to extend the advanced DC/OS install methods of deployment, such that there would be a Windows and Linux bootstrap node which allows Linux masters to be deployed, along with both Linux and Windows agents.

An extended goal is to extend our current acs-engine model to allow the deployment of these bootstrap nodes and to deploy the masters and agents automatically from these bootstrap nodes.

## Building DC/OS packages for Windows

Currently Windows packages for the acs-engine deployment in Azure are done on a Jenkins server. Build scripts are located [here](https://github.com/dcos/dcos-windows/tree/master/scripts), although these are likely to go away soon in preference of using pkgpanda for building.

## pkgpanda for Windows

### Software requirements for building

* Windows Server RS3 or later. Client SKUs are not sufficient because Docker does not support the necessary isolation mode that allows the builds to succeed. This may become possible going forwards, but as of now they do not work. Older versions of Windows Server will not work either as features needed are not present. As of the writing of this document, I am using Windows Server Version 10.0.16299.15.
* [git for Windows](https://git-scm.com/download/win) for getting this git repo.
* [bsdtar.exe](https://github.com/libarchive/libarchive) is used for creating and extracting tar files during the builds. It will soon handle the zip files. You will need to build this per the instructions on the github web site and need to make sure bsdtar.exe is in your path. There are versions that are distributed via install packages on the web, but these are generally really old and do not support everything that is required from pkgpanda.
* [Docker for Windows](https://docs.docker.com/docker-for-windows/install/) is required for building as individual packages are built within a docker container. As of the writing of this document you will need the Edge version as the Stable version does not work as well.
* [Python version 3.6 for Windows](https://www.python.org/downloads/release/python-364/) for running pkgpanda builds. 32 bit or 64-bit should work fine.

### Building

After you pull down the source using the git client change into your source directory and run `powershell.exe -file .\build_local_windows.ps1`. If you have everything installed the build will progress. Initially it builds a docker container necessary for building the packages. This is likely to take a while as it needs to download Windows Server Core RS3 builds, along with all the build tools necessary for all the packages.

Then it goes through each package in turn pulling down the necessary sources and components that package needs.

Finally the build goes through all the configuration templates and generates the necessary configuration for the packages. Note that as of this writing configuration is temporary placeholders, but by completion the necessary configuration will be in place.

### Design considerations

pkgpanda was written with Linux in mind and so the following high level concepts need to be ported to Windows equivalent concepts:

* We added a constance called `is_windows` that is used throughout the code to differentate Windows and Linux specific code.
* On Windows, file paths start with a drive letter (for instance `c:\`). On Linux a file path starts with just `/`. File and directory separators go in different directions. On Windows, some components support back-slash and forward-slash in a file path, but other components and libraries do not. We generally try to use the correct type on both platforms, but sometimes underlying APIs or code may use the Linux version and when calling to something that requires back-slash we do a quick search through the string and convert it.
* Linux Bash scripts and commands versus Windows scripts and commands are different. Sometimes they behave a little different so we need extra pre-conditions to make sure they do not fail. These changes are wrapped in the `is_windows` conditions. As a general rule, Linux bash scripts end with .sh. On Windows we have converted these scripts to PowerShell scripts which end with .ps1. Where possible we have modelled these scripts on the linux equivalents.
* Docker works differently on Windows to Linux. Generally they are features that just have not been implenented yet. Examples include mounting files on a docker container, and having overlapping directory mounts. These are being worked around specifically on Windows, and generally Linux is left to work the way they currently do.
* Windows packages are build as a package variant. [See the documentation](https://github.com/dcos/dcos/blob/master/pkgpanda/docs/tree_concepts.md#package-variants) for more details on that.
* Configuration .yaml files are duplicated for Windows. Currently these files hold placeholder data, but going forwards these will be updated to have more complete windows based configuration.
* Linux uses systemd for starting and stopping services. This is not available on Windows. A package is present that does some of the service management that the systemd service does on Linux, although it is not a complete substitute.
* Logging on Linux is done through systemd journaling. This is not present on Windows and so log files are used.
* AWS is not supported at this time for deployment of Windows agent and no effort has been put in to make this work.
* Where possible on Windows we have tried to install packages rather than building them from source.

### Things that are not complete

* The list of packages we build are those services we currently deploy today and are not more packages will be needed. Some packages are not deal with yet, such as the mkpanda python package which is used to build and deploy DC/OS.
* Installation of packages is done out-of-band using a set of custom scripts that do not reside in this repository. For example Mesos install script is located [here](https://github.com/dcos/dcos-windows/blob/master/scripts/mesos-agent-setup.ps1). This will be transitioned over to pkgpanda once all packages are fully built and configured properly.
* Configuration for the packages are placeholders and will be updated soon with real configuration.
* Although packages are built, no packages that depend on other packages have been built on Windows.  pkgpanda still needs some changes to support this as there are still linux only dependency information generated which cannot be consumed by the powershell scripts. An example of this would be the many python libraries which are needed to have mkpanda work on Windows. These libraries require python to be installed in a specified directory, and then that python package install would be mounted into the docker container while dealing with the python library package. As the dependencies do not work, these python libraries would not be buildable and installable.
