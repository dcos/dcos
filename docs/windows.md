---
post_title: >
    Design: Installation (Windows)
nav_title: Installation (Windows)
menu_order: 5
---
- *Note: This is a description of a feature in progress. In order to see the status of specific changes, please refer to* [Way Forward](#way-forward)

The installation design of DC/OS on Linux and Linux-like systems is covered in [docs](https://dcos.io/docs/overview/design/installation/). 
Build, installation and update The windows environment necessitates a number of changes to that design.
- Windows has no native support tar files, but does for zip file, so a tar utility and
  associated filters must be included in the packages directory.
- Windows has no make utility, so it must be brought in.
- Windows does not have native support for bash, but does for PowerShell.
- Windows does not have native support for utilities like curl, wget, grep, awk, sed and the such, but does for near-equivalent PowerShell cmdlets which can fulfill the same function. 
- Windows does not support some os specific python modules, but has support for most others. 
- There are differences between windows and Linux/unix handle semantics and ioctls.
- There are differences in file system semantics and file system conventions (i.e, "/opt/mesosphere" vs "c:/Mesosphere")
- Windows does not support systemd or journald.
- Windows docker operation is very different from Linux
- Many of the packages used in the Linux deployment are different in the windows environment.
- Windows machines usually prefer pre-built packages rather than in-situ builds from source.

## Design Goals

The design goals of goals of the Windows deployment are:
- Make differences as consistent and predictable as possible. In principle a Linux DC/OS system administrator should be able to learn a few transformation rules between the two environments and predict how to install, modify and operate a Windows host using the same skills they have already developed in Linux.
- Make the deployment also Windows native. A Windows sysadmin should be able to apply their knowledge hand habits as much as possible.
- Make the deployment functionally equivalent (so far as possible) to the Linux deployment.  A DC/OS UI user should not be able to obviously tell the difference between a Linux and windows host without looking at the host attributes.

The installation adds to those goals:
- The deployment should be feasible on a Windows host without additional preparation. As a result, the deployment must use only tools available on a freshly installed windows machine.

## changes to the dcos/dcos repository

The package tree, top level scripts, and configuration files are, as much as possible, organised in a parallel manner to the
Linux build process, but they are not the same, so shell scripts are shadowed by PowerShell scripts of the same name, ie build_local becomes build_local.ps1, prep_local becomes prep_local.ps1 and so on.  

- For the package tree. 
  - In each directory we have a windows.buildinfo.json parallel to the Linux buildinfo.json, but usually different as windows requires different dependencies, packages, git repositories or branches, and commit shas from the Linux equivalent. 
  - The build script located in each of the package directories is paralleled by a windows.build.ps1 script which is functionally similar.
    
- Changes to the python code in pkgpanda, release, gen, dcos_installer, ssh and related directories are
  - is_windows variable so that all os-specific branches don't have to go through a string compare
  - replacement of shell check_calls to if is_windows: check_call <windows> else: check_call <Linux>
  - added constants for paths so that the windows and Linux paths need not require inline "if is_windows" sections.

- A parallel set of yaml templates.  These files are specialised by gen in the same manner as the windows version. The yaml
  templates are used to create processed configuration files for a particular build and deployment. The windows versions will
  be pretty much line by line different owing to the difference in the two OS environments. For example, all paths will be
  different, the syntax of environment setting is different, and windows has its own service manager making systemd units not
  applicable to the windows build.  In place of systemd unit files, we will have a number of PowerShell scripts to implement
  the same functionality so far as practical.

## Packaging

All of the components in DC/OS Windows are built into a single tar.xz file that eventually gets extracted to the Linux equivalent path on Windows. Currently that path is %SystemDrive%:/DCOS rather than /opt/mesosphere, but that will be revised shortly. The built artifact is deployed from a separate bootstrap URL from the Linux artifact. 


## Building

Like Linux, the master artifact must be assembled somehow. Because the DC/OS build is made up of a changing list of components, the build tooling ends up looking like its own little package manager. Each component must be built from source, configured in a repeatable fashion and then added into the master artifact. The use of docker in building the windows artifact is similar to docker use in the Linux build, however the docker container is setup very differently and must match the build of the Windows OS being used. 

A DC/OS package is defined by two files. In windows, these are PowerShell rather than bash scripts, but their function is identical: [`windows.build.ps1`][1] and [`windows.buildinfo.json`][2]. These state what must be downloaded and how to build it. At build time, the tool chain takes care of building, packaging and including all the artifacts required into the master zip file.

Because the dependent tools, packages, configuration, even formats are different between Windows and Linux, it is necessary to separately build the Linux and windows packages on the respective systems.




[1]: https://github.com/dcos/dcos/blob/master/packages/mesos/windows.build.ps1
[2]: https://github.com/dcos/dcos/blob/master/packages/mesos/windows.buildinfo.json
