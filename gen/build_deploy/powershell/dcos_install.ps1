<#
.SYNOPSIS
  Name: dcos_install.ps1
  The purpose of this script is to Download, Extract, Install DC/OS packages on Windows agent and start Winpanda of DC/OS cluster.

.DESCRIPTION
  The script will:
  - Create needed DC/OS directories on Windows machine
  - Download prerequisites.zip achive from provided $url to C:\dcos
  - Extract the archive
  - Install the pre-requisites: 7-zip
  - Unpack from DC/OS Windows Installer : Python, Winpanda
  - Create ScheduledTask to execute RunOnce.ps1
  - Create RunOnce.ps1 which will contain executor for Winpanda and clean the parent ScheduledTask
    !Note! RunOnce.ps1 is responsible to start Winpanda upon Windows reboot completion)

.PARAMETER bootstrap_url
  The url of Nginx web server started on Boostrrap agent to serve Windows installation files

.PARAMETER version
  DC/OS version

.PARAMETER masters
  A comma separated list of Master(s) IP addresses

.PARAMETER baseDir
  The initial directory which this example script will use C:\dcos

.NOTES
    Updated: 2019-11-08       Extended startup parameters to acommodate correct script run.
    Updated: 2019-09-03       Added dcos-install.ps1 which is addressed to install pre-requisites on Windows agent and run Winpanda.
    Release Date: 2019-09-03

  Author: Sergii Matus

.EXAMPLE
#  .\dcos_install.ps1 <bootstrap_url> <version> <masters>
#  .\dcos_install.ps1 "http://int-bootstrap1-examplecluster.example.com:8080" "1.13.0" "master1,master2"

# requires -version 2
#>

[CmdletBinding()]

# PARAMETERS
param (
    [Parameter(Mandatory=$true)] [string] $bootstrap_url,
    [Parameter(Mandatory=$true)] [string] $version,
    [Parameter(Mandatory=$true)] [string] $masters
)

# GLOBAL
$global:basedir = "C:\dcos"

$ErrorActionPreference = "Stop"

function Write-Log
{
    [CmdletBinding()]
    Param
    (
        [Parameter(Mandatory=$true,
                   ValueFromPipelineByPropertyName=$true)]
        [ValidateNotNullOrEmpty()]
        [Alias("LogContent")]
        [string]$Message,

        [Parameter(Mandatory=$false)]
        [Alias('LogPath')]
        [string]$Path='C:\dcos\var\log\dcos_install.log',

        [Parameter(Mandatory=$false)]
        [ValidateSet("Error","Warn","Info")]
        [string]$Level="Info",

        [Parameter(Mandatory=$false)]
        [switch]$NoClobber
    )

    Begin
    {
        # Set VerbosePreference to Continue so that verbose messages are displayed.
        $VerbosePreference = 'Continue'
    }
    Process
    {

        # If the file already exists and NoClobber was specified, do not write to the log.
        if ((Test-Path $Path) -AND $NoClobber) {
            Write-Error "Log file $Path already exists, and you specified NoClobber. Either delete the file or specify a different name."
            Return
            }

        # If attempting to write to a log file in a folder/path that doesn't exist create the file including the path.
        elseif (!(Test-Path $Path)) {
            Write-Verbose "Creating $Path."
            $NewLogFile = New-Item $Path -Force -ItemType File
            }

        else {
            # Nothing to see here yet.
            }

        # Format Date for our Log File
        $FormattedDate = Get-Date -Format "yyyy-MM-dd HH:mm:ss"

        # Write message to error, warning, or verbose pipeline and specify $LevelText
        switch ($Level) {
            'Error' {
                Write-Error $Message
                $LevelText = 'ERROR:'
                }
            'Warn' {
                Write-Warning $Message
                $LevelText = 'WARNING:'
                }
            'Info' {
                Write-Verbose $Message
                $LevelText = 'INFO:'
                }
            }

        # Write log entry to $Path
        "$FormattedDate $LevelText $Message" | Out-File -FilePath $Path -Append
    }
    End
    {
    }
}

function SetupDirectories() {
    # available directories
    $dirs = @(
        "$($basedir)",
        "$($basedir)\bootstrap",
        "$($basedir)\bootstrap\prerequisites",
        "$($basedir)\conf"
    )
    # setup
    Write-Log("Creating a directories structure:")
    foreach ($dir in $dirs) {
        if (-not (test-path "$dir") ) {
            Write-Log("$($dir) doesn't exist, creating it")
            New-Item -Path $dir -ItemType directory | Out-Null
        } else {
            Write-Log("$($dir) exists, no need to create it")
        }
    }
}

function Download([String] $url, [String] $file) {
    $output = "$($basedir)\bootstrap\$file"
    Write-Log("Starting Download of $($url) to $($output) ...")
    $start_time = Get-Date
    (New-Object System.Net.WebClient).DownloadFile($url, $output)
    Write-Log("Download complete. Time taken: $((Get-Date).Subtract($start_time).Seconds) second(s)")
}

function ExtractTarXz($infile, $outdir){
    if (-not (test-path "$env:ProgramFiles\7-Zip\7z.exe")) {
        throw "$env:ProgramFiles\7-Zip\7z.exe needed"
    }
    $sz = "$env:ProgramFiles\7-Zip\7z.exe"
    $Source = $infile
    $Target = $outdir
    Write-Log("Extracting $Source to $Target")
    $start_time = Get-Date
    $exec = ("`"{0}`" x `"{1}`" -so | `"{2}`" x -aoa -si -ttar -o`"{3}`"" -f $sz, $Source, $sz, $Target)
    Write-Log("Running: cmd /c $exec")
    & cmd /C $exec
    Write-Log("Extract complete. Time taken: $((Get-Date).Subtract($start_time).Seconds) second(s)")
}

function ExtractBootstrapZip($zipfile, $Target){
    $Source = $zipfile
    Write-Log("Extracting $Source to $Target")
    $start_time = Get-Date
    expand-archive -path "$Source" -destinationpath "$Target" -force
    Write-Log("Extract complete. Time taken: $((Get-Date).Subtract($start_time).Seconds) second(s)")
}

function CreateWriteFile([String] $dir, [String] $file, [String] $content) {
    Write-Log("vars: $dir, $file, $content")
    if (-not (test-path "$($dir)\$($file)") ) {
        Write-Log("Creating $($file) at $($dir)")
    }
    else {
        Write-Log("$($dir)\$($file) already exists. Re-writing")
        Remove-Item "$($dir)\$($file)"
    }
    New-Item -Path "$($dir)\$($file)" -ItemType File
    Write-Log("Writing content to $($file)")
    Add-Content "$($dir)\$($file)" "$($content)"
    Get-Content "$($dir)\$($file)"
}

function CreateRunOnceScheduledTask($dir, $masters_ip, $winagent_ip) {
    $destination = "$($dir)\RunOnce.ps1"
    if (-not (Test-Path $destination) ) {
        Write-Log("$($destination) missing. Creating")
        $RunOnceScript_content = "Set-Location -Path 'C:\winpanda';`n& pip install virtualenv;`n& virtualenv .venv;`n& .venv\Scripts\activate;`n& pip install -r C:\winpanda\requirements.txt;`n& python C:\winpanda\bin\winpanda.py setup;`n& python C:\winpanda\bin\winpanda.py start`n#Remove a Scheduled task RunOnce, created while initial provision`nif(Get-ScheduledTask -TaskName `"RunOnce`" -TaskPath '\CustomTasks\' -ErrorAction Ignore) { Unregister-ScheduledTask -TaskName `"RunOnce`" -Confirm:`$False }`n"
        CreateWriteFile "$($dir)" "RunOnce.ps1" $RunOnceScript_content

        Write-Log("Creating Scheduled Task to run Winpanda")
        $action = New-ScheduledTaskAction -Execute '%systemroot%\System32\WindowsPowerShell\v1.0\powershell.exe' -Argument $destination
        $trigger = New-ScheduledTaskTrigger -AtStartup
        $principal = New-ScheduledTaskPrincipal -UserID "NT AUTHORITY\SYSTEM" -LogonType ServiceAccount -RunLevel Highest
        Register-ScheduledTask -TaskName 'RunOnce' -TaskPath '\CustomTasks\' -Action $action -Trigger $trigger -Principal $principal -Description 'Winpanda task to run once after winagent provision.' -ErrorAction Stop
    } else {
        Write-Log("$($dir)\RunOnce.ps1 already exists. Skipping")
    }
}

function main($url, $version, $masters) {
    SetupDirectories

    Write-Log("Downloading/Extracting prerequisites.zip out of Bootstrap agent ...")
    Download "$url/$version/genconf_win/serve/prerequisites/prerequisites.zip" "prerequisites.zip"
    $zipfile = "$($basedir)\bootstrap\prerequisites.zip"
    ExtractBootstrapZip $zipfile "$($basedir)\bootstrap\prerequisites"

    Write-Log("Installing 7zip from prerequisites.zip ...")
    & cmd /c "start /wait $($basedir)\bootstrap\prerequisites\7z-x64.exe /S" 2>&1 | Out-File C:\dcos\var\log\dcos_install.log -Append

	Write-Log("Checking proper versions from latest.package_list.json ...")
	Download "$url/$version/genconf_win/serve/package_lists/latest.package_list.json" "latest.package_list.json"
	$package_list_json = "$($basedir)\bootstrap\latest.package_list.json"
	echo $(cat $package_list_json | ConvertFrom-Json) | Where-Object { $_ -Match "python"} | New-Variable -Name python_package
	echo $(cat $package_list_json | ConvertFrom-Json) | Where-Object { $_ -Match "winpanda"} | New-Variable -Name winpanda_package

	Write-Log("Installing Python from Bootstrap agent - $($python_package).tar.xz...")
    Download "$url/$version/genconf_win/serve/packages/python/$($python_package).tar.xz" "python.tar.xz"
    $pythontarfile = "$($basedir)\bootstrap\python.tar.xz"
    ExtractTarXz $pythontarfile "C:\python36"
    setx PATH "$env:path;C:\python36;C:\python36\scripts" -m
    & RefreshEnv.cmd

    Write-Log("Installing Winpanda from Bootstrap agent - $($winpanda_package).tar.xz ...")
    Download "$url/$version/genconf_win/serve/packages/winpanda/$($winpanda_package).tar.xz" "winpanda.tar.xz"
    $winpandatarfile = "$($basedir)\bootstrap\winpanda.tar.xz"
    ExtractTarXz $winpandatarfile "C:\"

    # Fill up Ansible inventory content to cluster.conf
    Write-Log("MASTERS: $($masters)")
    [System.Array]$masterarray = $masters.split(",")
    $masternodecontent = ""
    for ($i=0; $i -lt $masterarray.length; $i++) {
        $masternodecontent += "[master-node-$($i+1)]`nPrivateIPAddr=$($masterarray[$i])`nZookeeperListenerPort=2181`n"
    }
    $local_ip = (Get-WmiObject -Class Win32_NetworkAdapterConfiguration | where {$_.DefaultIPGateway -ne $null}).IPAddress | select-object -first 1
    Write-Log("Local IP: $($local_ip)")
    $content = "$($masternodecontent)`n[distribution-storage]`nRootUrl=$($bootstrap_url)`nPkgRepoPath=$($version)/genconf_win/serve`nPkgListPath=latest.package_list.json`n[local]`nLocalPrivateIPAddr=$($local_ip)"
    CreateWriteFile "$($basedir)\conf" "cluster.conf" $content

    # Creating RunOnce scheduled task along with the RunOnce.ps1 script
    CreateRunOnceScheduledTask $basedir $masters $local_ip
}

main $bootstrap_url $version $masters
