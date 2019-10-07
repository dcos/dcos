<#
.SYNOPSIS
  Name: dcos_install.ps1
  The purpose of this script is to Download, Extract, Install DC/OS packages on Windows agent and start Winpanda of DC/OS cluster.

.DESCRIPTION
  The script will:
  - Create needed DC/OS directories on Windows machine
  - Download *.zip achive from provided $url to C:\dcos
  - Extract the archive
  - Install pre-requisites using choco: 7-zip, nssm, vcredist, git, python
  - create ScheduledTask to execute RunOnce.ps1
  - create RunOnce.ps1 which will contain executor for Winpanda and clean the parent ScheduledTask
  - #TO DO: Setup Mesos-DNS

.PARAMETER InitialDirectory
  The initial directory which this example script will use C:\dcos

.PARAMETER Add
  A switch parameter that will cause the example function to ADD content.

Add or remove PARAMETERs as required.

.NOTES
    Updated: 2019-09-03       Added dcos-install.ps1 which is addressed to install pre-requisites on Windows agent and run Winpanda.
    Release Date: 2019-09-03

  Author: Sergii Matus

.EXAMPLE
#  .\dcos_install.ps1 https://dcos-win.s3.amazonaws.com/bootstrap.zip "master1, master2"

# requires -version 2
#>

[CmdletBinding()]

# PARAMETERS
param (
    [string] $url,
    [string] $masters
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
        "$($basedir)\var",
        "$($basedir)\var\log",
        "$($basedir)\var\opt",
        "$($basedir)\var\run",
        "$($basedir)\work",
        "$($basedir)\images",
        "$($basedir)\bootstrap",
        "$($basedir)\chocolatey_offline",
        "$($basedir)\packages",
        "$($basedir)\active",
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

function ExtractTarXz($infile){
    if (-not (test-path "$env:ProgramFiles\7-Zip\7z.exe")) {
        throw "$env:ProgramFiles\7-Zip\7z.exe needed"
    }
    Set-Alias sz "$env:ProgramFiles\7-Zip\7z.exe"
    $Source = $infile
    $Target = $(Split-Path -Path $infile)
    Write-Log("Extracting $Source to $Target")
    $start_time = Get-Date
    & cmd.exe "/C 7z x $Source -so | 7z x -aoa -si -ttar -o$Target"
    # TO DO:
    # handle validation of tar.xz , as "cmd 7z" is quite poor on such functionality. Message: Open ERROR: Can not open the file as [xz] archive
    Write-Log("Extract complete. Time taken: $((Get-Date).Subtract($start_time).Seconds) second(s)")
}

function RunWinpandaSetup($dir, $action){
    Write-Log("What's Next? Run 'python.exe $($dir)\winpanda.py $($action)' which Ol.Belov/An.Borysov are working on.")
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

function CreateRunOnceReg($dir, $masters_ip, $winagent_ip) {
    if (-not (test-path "$($dir)\RunOnce.ps1") ) {
        Write-Log("$($basedir)\RunOnce.ps1 missing. Creating")
        $RunOnceScript_content = "& pip install virtualenv;`n& virtualenv .venv;`n& .venv\Scripts\activate;`n& pip install -r C:\dcos\chocolatey_offline\winpanda\requirements.txt;`n& python C:\dcos\chocolatey_offline\winpanda\cli.py setup --master-private-ipaddr $($masters_ip) --local-private-ipaddr $($winagent_ip)`n"
        CreateWriteFile "$($basedir)" "RunOnce.ps1" $RunOnceScript_content
        Write-Log("Creating RunOnce registry record")
        $KeyName = 'Run'
        $Command = "%systemroot%\System32\WindowsPowerShell\v1.0\powershell.exe -executionpolicy bypass -file `"$($dir)\RunOnce.ps1`""
        if (-not ((Get-Item -Path HKLM:\Software\Microsoft\Windows\CurrentVersion\RunOnce).$KeyName )) {
            New-ItemProperty -Path 'HKLM:\Software\Microsoft\Windows\CurrentVersion\RunOnce' -Name $KeyName -Value $Command -PropertyType ExpandString
        }
        else {
            Set-ItemProperty -Path 'HKLM:\Software\Microsoft\Windows\CurrentVersion\RunOnce' -Name $KeyName -Value $Command -PropertyType ExpandString
        }
    } else {
        Write-Log("$($dir)\RunOnce.ps1 already exists. Skipping")
    }
}

function CreateRunOnceScheduledTask($dir, $masters_ip, $winagent_ip) {
    $destination = "$($dir)\RunOnce.ps1"
    if (-not (Test-Path $destination) ) {
        Write-Log("$($destination) missing. Creating")
        $RunOnceScript_content = "& pip install virtualenv;`n& virtualenv .venv;`n& .venv\Scripts\activate;`n& pip install -r C:\dcos\chocolatey_offline\winpanda\requirements.txt;`n& python C:\dcos\chocolatey_offline\winpanda\cli.py setup --master-private-ipaddr $($masters_ip) --local-private-ipaddr $($winagent_ip)`n#Remove a Scheduled task RunOnce, created while initial provision`nif(Get-ScheduledTask -TaskName `"RunOnce`" -TaskPath '\CustomTasks\' -ErrorAction Ignore) { Unregister-ScheduledTask -TaskName `"RunOnce`" -Confirm:`$False }`n"
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

function SetupMesosDNS($masters_ip) {
    Write-Log("Mesos-DNS setup with following $masters_ip")
    #TO DO: Mesos-DNS logic to be placed here
}

function main($uri, $masters) {
    SetupDirectories

    # Downloading/Extracting bootstrap.zip out of AWS S3 bucket
    Download $uri "bootstrap.zip"
    $zipfile = "$($basedir)\bootstrap\bootstrap.zip"
    ExtractBootstrapZip $zipfile "$($basedir)\chocolatey_offline"

    ### The block for BETA Phase 1.1 ###
    # Installing chocolatey. TO DO : remove in Phase 1.2
    Write-Log("Installing Chocolatey now ...")
    & "$($basedir)\chocolatey_offline\install_choco.ps1" 2>&1 | Out-File C:\dcos\var\log\dcos_install.log -Append
    # Installing 7zip, Python3, NSSM, VCredist140
    Write-Log("Chocolatey starts installing dependencies ...")
    & cmd.exe "/C chocolatey install 7zip.install 7zip -s $($basedir)\chocolatey_offline --yes" 2>&1 | Out-File C:\dcos\var\log\dcos_install.log -Append
    & cmd.exe "/C chocolatey install python3 -s $($basedir)\chocolatey_offline --yes" 2>&1 | Out-File C:\dcos\var\log\dcos_install.log -Append
    ## TO DO : remove in Phase 1.2
    & cmd.exe "/C chocolatey install nssm -s $($basedir)\chocolatey_offline --yes" 2>&1 | Out-File C:\dcos\var\log\dcos_install.log -Append
    & cmd.exe "/C chocolatey install vcredist140 -s $($basedir)\chocolatey_offline --version=14.22.27821 --yes" 2>&1 | Out-File C:\dcos\var\log\dcos_install.log -Append
    ##

    # Fill up Ansible inventory content to cluster.conf
    Write-Log("MASTERS: $($masters)")
    $masternode = foreach ($item in $masters.split(",")) {
        "MasterNode=$item`n"
    }
    $local_ip = (Get-WmiObject -Class Win32_NetworkAdapterConfiguration | where {$_.DefaultIPGateway -ne $null}).IPAddress | select-object -first 1
    Write-Log("Local IP: $($local_ip)")
    $content = "[main]`n$($masternode)DistributionStorageURL=https://wintesting.s3.amazonaws.com/testing/`nLocalPrivateIPAddr=$($local_ip)`nZookeeperListenerPort=2181"
    CreateWriteFile "$($basedir)\conf" "cluster.conf" $content

    #CreateRunOnceReg $basedir $masters $local_ip
    CreateRunOnceScheduledTask $basedir $masters $local_ip

    #TO DO: Setup Mesos-DNS
    #SetupMesosDNS $masters
}

main $url $masters