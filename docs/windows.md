# DC/OS on windows

DC/OS on Windows is at a stage where deployment and upgrades of Windows nodes now work.  Using a version of dcos-engine (formally acs-engine) that has been updated for this change, both  Windows and Linux bootstrap nodes can be deployed, and following that Linux masters are deployed along with both Windows and Linux agents. Once deployed dcos-engine can then perform upgrades of this deployment, first by upgrading the boostrap nodes, then upgrading the masters, and finally going to the Linux and Windows agents and upgrading each of them.

## The high-level goal of DC/OS on Windows

The goal of the Windows port of this project is to give close to the same level of pkgpanda functionality that is supported with Linux, with as few exceptions as possible. This means building of DC/OS on Windows followed by deployment of DC/OS via dcos-engine to install Linux bootstrap nodes, masters and agents, along with the new Windows boostrap nodes and Windows agents. Once installed these deployments should be upgradable via dcos-engine.

As part of the pkgpanda deployment of Windows components onto the Windows bootstrap node and Windows agents, deployment of those services that have been ported to Windows are being installed, including Mesos, DCOS-Net, DCOS-Diagnostics, DCOS-Metrics and the DCOS-AdminRouter. Although these components have been ported, some Windows functionality may be different from Linux due to platform differences, as well as the prioritization of what was thought to be necessary.

Once installed the Windows nodes can process Windows based workloads based on Windows based constraints and report the necessary status back to the master node.

## How to install

**NOTE:** `Windows Server Core version 1803 with Containers` is the Windows SKU in Azure we use. This brings the Windows RS4 server image that is needed, along with pre-installed Docker that works on this machine. Older and newer versions of Windows Server Core are not compatible with the bootstrap docker container, or the nginx docker container used for deployment. This is due to the fact that Windows docker containers are locked in to specific Windows releases.

As of the writing of this document, the only way of installing DC/OS with Windows agents is using [dcos-engine](https://github.com/Azure/dcos-engine/blob/master/docs/README.md), although it can be manually installed. Example .json configuration files are present in the [dcos-engine example directory](https://github.com/Azure/dcos-engine/tree/master/examples/windows).  Once installed, specifying a service constraint of `os=windows` will allow a service to be sent to a windows agent. Not specifying a contstraint at all may cause a service to be launched on either a Windows or Linux agent.

This installation approach allows you to deploy a specific version of DC/OS in an Azure environment with a set of Linux masters, and a set of public and private Linux/Windows agents. The Windows and Linux machines are installed from a bootstrap node allowing easier addition of agents, as well as allowing upgrades of all nodes.

## Building DC/OS packages for Windows

pkgpanda builds Windows packages in the same way as Linux. To simplfy the process a PowerShell script is supplied in the root of the repo called `build_local_windows.ps1`. The result of the build very similar to that of a Linux build producing all the package artifacts as well as the bootstrap and agent deployment scripts and configuration.

Differing from Linux where `dcos_generate_config.sh` is produced with the bootstrap tarball encoded at the end, Windows produces a compressed tarball `dcos_generate_config.windows.tar.xz`. This contains the Windows docker container with the Windows bootstrap node embedded in it, along with a script to run it called dcos_generate_config.ps1



## pkgpanda for Windows

### Software requirements for building

* Windows Server Core RS4. Newer and older versions of Windows Server will not work because pkgpanda docker files are locked into RS4 only at this time.

* [git for Windows](https://git-scm.com/download/win) for getting this git repo. Note: Git symlink support is required for building and testing, so needs to be enabled when enlisting. This can be done via `git clone -c core.symlinks=true <URL>`

* [7-Zip](https://www.7-zip.org/download.html) is used for creating and extracting tar/zip files during the builds.

* [Docker Enterprise edition for Windows](https://docs.docker.com/install/windows/docker-ee/) is required for building individual packages within a docker container. Only enterprise edition is supported on Windows Server.

* [Python version 3.6.5 for Windows](https://www.python.org/downloads/release/python-365/) for running pkgpanda builds. 64-bit version should be used. TOX unittests are locked into this version. NOTE: Long filename support is required for Python to function properly. This can be achieved in PowerShell with this command: ```New-Item -Path "HKLM:\SYSTEM\CurrentControlSet\Control\FileSystem\" -Name LongPathsEnabled -Value 1```. A reboot will be required after this stage to enable it.

### Building

After you pull down the source using the git client change into your source directory and run `powershell.exe -file .\build_local_windows.ps1`. If you have everything installed the build will progress. Initially it builds a docker container necessary for building the packages. This is likely to take a while as it needs to download Windows Server Core RS4 docker file, along with all the build tools necessary for building all the packages.

Then it goes through each package in turn pulling down the necessary sources and components that package needs.

Then the build goes through all the configuration templates and generates the necessary configuration for the packages. Note that as of this writing configuration is temporary placeholders, but by completion the necessary configuration will be in place.

Finally it generates the bootstrap node docker file and uploads all artifacts to the configured clound storage accounts.

**Important Note: If the same `dcos-release.config.yaml` file is used for Linux and Windows, artifact uploads by Windows and Linux will interfere with each other as upload files will often match across platforms.**

### Deploying DCOS

Deployment of the Windows bootstrap node works in a similar way to that of Linux, except instead of downloading a script with the bootstrap embedded in the script we have an archive with a docker image and a file in it. The following powershell code is an example of how to download and run the bootstrap script:

```powershell.exe
    # Create a directory to download and run the bootstrap configuration from
    New-item -itemtype directory -erroraction silentlycontinue c:\dcos
    cd c:\dcos

    # Create a genconf directory
    New-item -itemtype directory -erroraction silentlycontinue genconf

    # In the c:\dcos\genconf a config.yaml needs to be created, along with
    # an ip-detect.ps1 script that the config.yaml file points to. Refer to Mesospere DCOS install documentation for more details.
    # <This is a manual step>

    # Download the compressed tarball
    curl.exe -O <url_to_tarball>/dcos_generate_config.windows.tar.xz

    # Extract the docker image and install script. Note that you will need
    # to install 7-Zip from https://www.7-zip.org/download.html.
    # Extraction looks like this:
    & cmd /c "$env:ProgramFiles\7-zip\7z.exe e dcos_generate_config.windows.tar.xz -so | $env:ProgramFiles\7-zip\7z.exe x -si -ttar"

    # Run the extracted script to load and run the docker image
    & dcos_generate_config.ps1

```

The generation of the `config.yaml` file will be similar to that on Linux except the `ip-detect` entry needs to point to a powershell script. Examples of `ip-detect.ps1` scripts are in `gen\ip-detect` source directory.

Generation of the upgrade script is the same as on a Linux bootstrap node, namely `dcos_generate_config.ps1 --generate-node-upgrade-script <installed_cluster_version>` after creating the genconf directory and associated config.yaml and ip-detect.ps1 files.

After generating the configuration and serve directory with associated artifacts for install or upgrade, a web server is needed to server the files in the same way as Linux. We have achieved this in dcos-engine by running the following few lines of code to pull down a Windows based nginx container and launching it:

```powershell.exe
    # Create docker directory for Windows nginx
    New-item -itemtype directory -erroraction silentlycontinue c:\docker
    cd c:\docker

    # download the docker file
    & curl.exe --keepalive-time 2 -fLsSv --retry 20 -Y 100000 -y 60 -o c:\docker\dockerfile https://dcos-mirror.azureedge.net/winbootstrap/dockerfile
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to download dockerfile"
    }

    # Download the nginx config file
    & curl.exe --keepalive-time 2 -fLsSv --retry 20 -Y 100000 -y 60 -o c:\docker\nginx.conf https://dcos-mirror.azureedge.net/winbootstrap/nginx.conf
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to download nginx.conf"
    }

    # only create dcosnat if it does not exist.
    $a = docker network ls | select-string -pattern "dcosnat"
    if ($a.count -eq 0)
    {
        & docker.exe network create --driver="nat" --opt "com.docker.network.windowsshim.disable_gatewaydns=true" "dcosnat"
        if ($LASTEXITCODE -ne 0) {
            throw "Failed to create dcosnat docker network"
        }
    }

    # Build the nginx container
    & docker.exe build --network dcosnat -t nginx:1803 c:\docker
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to build docker image"
    }

    # Run the Windows nginx container against the genconf/serve directory
    # that was generated from the dcos_generate_config.ps1
    & docker.exe run --rm -d --network dcosnat -p 8086:80 -v C:/dcos/genconf/serve/:c:/nginx/html:ro nginx:1803
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to run docker image"
    }
```

And now there is a web server running on the bootstrap node serving artifacts from port 8086. Note that this port may need to be opened in the firewall so agents can access the artifacts.

Windows agents are then set up by downloading the dcos_install.ps1 or upgrade scripts from the bootstrap node. An example set of commands are as follows:

```powershell.exe
    # Example of download from bootstrap node:
    curl.exe -O http://<bootstrap_ip>:8086/dcos_install.ps1

    # Executing the script with either slave or slave_public option:
    .\dcos_install.ps1 slave_public

    # Example of download the upgrade script. Note the path of the upgrade
    # script is displayed as part of the dcos_generate_config.ps1 run:
    curl.exe -O http://>bootstrap_ip>:8086/upgrade/<upgrade_hash>/dcos_node_upgrade.ps1

    # Executing the upgrade script:
    .\dcos_node_upgrade.ps1
```

### Design considerations

pkgpanda was written with Linux in mind and so the following high level concepts need to be ported to Windows equivalent concepts:

* We added a constant called `is_windows` that is used throughout the code to differentate Windows and Linux specific code.
* On Windows, file paths start with a drive letter (for example `c:\`). On Linux a file path starts with just `/`. File and directory separators go in different directions. On Windows, some components support back-slash and forward-slash in a file path, but other components and libraries do not. We generally try to use the correct type on both platforms, but sometimes underlying APIs or code may use the Linux version and when calling to something that requires back-slash we do a quick search through the string and convert it.
* Linux Bash scripts and commands versus Windows scripts and commands are different. Sometimes they behave a little different so we need extra pre-conditions to make sure they do not fail. These changes are wrapped in the `is_windows` conditions. As a general rule, Linux bash scripts end with .sh. On Windows we have converted these scripts to PowerShell scripts which end with .ps1. Where possible we have modelled these scripts on the linux equivalents.
* Docker works differently on Windows to Linux. Docker images are tighed into an operating system version which is why the Windows docker files in the build only work on Server Core RS4 1803.
* Windows packages are build as a `Windows` package variant. [See the documentation](https://github.com/dcos/dcos/blob/master/pkgpanda/docs/tree_concepts.md#package-variants) for more details on that.
* Configuration .yaml files are duplicated for Windows. Only those configurations that are related to the functionality supported on Windows has been ported..
* Linux uses systemd for starting and stopping services. New binaries for Windows have been developed that act like systemd service starting and stopping. As such there is a systemctl.exe included in DC/OS and a binary called systemctl-exec.exe which is a service wrapper that can run the DC/OS binaries in a way similar to that on Linux. Note that this is not native to the operating system and so sometimes we have to pre-provision the machine with these binaries in order to install the Windows DC/OS agent.
* Logging on Linux is done through systemd journaling. This is not present on Windows and so log files are used.
* AWS is not supported at this time for deployment of Windows agent and no effort has been put in to make this work.
* Where possible on Windows we have tried to install packages rather than building them from source.
* 7-zip is used throughout to do all compression and taring. tar on Linux can tar and compress in one step where on Windows 7-zip does this in two steps, one to tar then one to compress.
* Symbolic links work differently on Windows to Linux. Where symlinks are followable on Linux where they are not on Windows. Therefore where symlinks are used on Linux, directories in Windows are linked through Junctions, and files through Hard links.  Junctions are almost hard links for directories although the semantics are slightly different. Unfortunately Python does not support Windows junctions and all functions related to symbolic links in Python had to be overloaded on Windows to call out to tools that support the necessary functionality.
* The Windows file system works very differently from Linux in one key way, namely that of if a file is open somewhere (running, for example), it cannot be deleted. Similar problems also occur around the renaming of files that are open. With this in mind, imagine a virus checker that is running on the Windows machine while a build is happening and lots of files are being created, renamed and deleted.  On top of that, Windows file system has got a little bit of asynchronicity to it, such that when a process has a file open, when the process exits that file may still be marked as in use for a very short amount of time after that.  These problems have caused many problems throughout the porting of pkgpanda to Windows and you will sometimes see retry loops when files are being deleted or renamed. On top of this, Python does not support Junctions and hard links well on Windows making recursive directory removal difficult requiring call out code to Windows command line tools.
