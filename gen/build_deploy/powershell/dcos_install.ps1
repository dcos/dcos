<#
.SYNOPSIS
  Name: dcos_install.ps1
  The purpose of this script is to Download, Extract, Install DC/OS packages on Windows agent and start Winpanda of DC/OS cluster.

.DESCRIPTION
  The script will:
  - Create needed DC/OS directories on Windows machine
  - Download prerequisites.zip achive from provided $url to $install_dir
  - Extract the archive
  - Install the pre-requisites: 7-zip
  - Unpack from DC/OS Windows Installer following packages: Python, Winpanda
  - Set needed Env variables for Python
  - Run Winpanda.py with flags: Setup & Start

.PARAMETER bootstrap_url
  [Required] The url of Nginx web server started on Boostrrap agent to serve Windows installation files

.PARAMETER masters
  [Required] A comma separated list of Master(s) IP addresses

.PARAMETER install_dir
  [Optional] DC/OS installation root directory. Default value is C:\d2iq\dcos

.PARAMETER var_dir
  [Optional] DC/OS variable directory for a files created by bootstrap process, for logs stored. Default value is C:\d2iq\dcos\var

.NOTES
    Updated: 2020-01-17       Added LongPathsSupport function that enables support of pathes longer 256 simbols. 
    Updated: 2019-11-29       Added install_dir and var_dir into path.json file for more flexible DC/OS configuration. Replaced conf dir with etc.
    Updated: 2019-11-22       Removed RunOnce.ps1 and Scheduled task logic. Fixed cluster.conf parameters. Added download of detect_ip*.ps1 scripts.
    Updated: 2019-11-08       Extended startup parameters to acommodate correct script run.
    Updated: 2019-09-03       Added dcos-install.ps1 which is addressed to install pre-requisites on Windows agent and run Winpanda.
    Release Date: 2019-09-03

  Author: Sergii Matus

.EXAMPLE
#  .\dcos_install.ps1 <bootstrap_url> <masters>
#  .\dcos_install.ps1 "http://int-bootstrap1-examplecluster.example.com:8080/<version>/genconf/serve" "master1,master2"

# requires -version 2
#>

[CmdletBinding()]

# PARAMETERS
param (
    [Parameter(Mandatory=$true)] [string] $bootstrap_url,
    [Parameter(Mandatory=$true)] [string] $masters,
    [Parameter(Mandatory=$false)][string] $install_dir = 'C:\d2iq\dcos',
    [Parameter(Mandatory=$false)][string] $var_dir = 'C:\d2iq\dcos\var'
)

# GLOBAL
$global:basedir = "$($install_dir)"
$global:vardir  = "$($var_dir)"

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
        [string]$Path="$($vardir)\log\dcos_install.log",

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
        "C:\d2iq",
        "C:\d2iq\dcos",
        "C:\d2iq\dcos\etc",
        "$($basedir)",
        "$($basedir)\bootstrap",
        "$($basedir)\bootstrap\prerequisites",
		"$($basedir)\bin",
        "$($basedir)\etc",
        "$($vardir)",
        "$($vardir)\log"
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

function Add-EnvPath {
    param(
        [Parameter(Mandatory=$true)]
        [string] $Path,

        [ValidateSet('Machine', 'User', 'Session')]
        [string] $Container = 'Session'
    )

    if ($Container -ne 'Session') {
        $containerMapping = @{
            Machine = [EnvironmentVariableTarget]::Machine
            User = [EnvironmentVariableTarget]::User
        }
        $containerType = $containerMapping[$Container]

        $persistedPaths = [Environment]::GetEnvironmentVariable('Path', $containerType) -split ';'
        if ($persistedPaths -notcontains $Path) {
            $persistedPaths = $persistedPaths + $Path | where { $_ }
            [Environment]::SetEnvironmentVariable('Path', $persistedPaths -join ';', $containerType)
        }
    }

    $envPaths = $env:Path -split ';'
    if ($envPaths -notcontains $Path) {
        $envPaths = $envPaths + $Path | where { $_ }
        $env:Path = $envPaths -join ';'
    }
}

function SetupPathJson([String] $pathsJson) {
    $jsonDoc = [pscustomobject]@{
        install = "$($basedir)"
        var = "$($vardir)"
    }
    if (-not (test-path "$($pathsJson)") ) {
        Write-Log("$($pathsJson) doesn't exist, creating it")
        [System.IO.File]::WriteAllLines($pathsJson, ($jsonDoc | convertTo-Json))
    }
    else {
        Write-Log("$($pathsJson) already exists, checking if such contains correct values")
        $previousJsonDoc = [System.IO.File]::ReadAllLines( ( Resolve-Path $pathsJson ) ) | ConvertFrom-Json
        Write-Verbose "JSON File Opened ."
	    if (-not (($previousJsonDoc.install -eq $jsonDoc.install) -and ($previousJsonDoc.var -eq $jsonDoc.var))) {
	    	Write-Log("$($pathsJson) doesn't match to expected, changing it.")
	    	Write-Verbose "Opening JSON file for write (locking) ..."
            while ($true) {
                try {
                    $file = [System.IO.StreamWriter] ([string] $pathsJson)
                    Write-Verbose "JSON File Opened and Locked."
                    break
                }
	    		catch {
                    Write-Warning "Error Opening/Locking JSON File: $($Error[0].Exception.InnerException.Message)"
                    Write-Verbose "Trying again ..."
                    Start-Sleep -Milliseconds 1000
                }
            }
            Write-Verbose "Writing JSON ..."
            $file.WriteLine($($jsonDoc | ConvertTo-Json))
            Write-Verbose "Closing JSON ..."
            $file.Close()
        }
	}
}

function LongPathsSupport {
    $registryPath = "HKLM:\SYSTEM\CurrentControlSet\Control\FileSystem"
    $Name = "LongPathsEnabled"
    $value = "1"
    if(!(Test-Path $registryPath)) {
        
		New-Item -Path $registryPath -Force | Out-Null
        New-ItemProperty -Path $registryPath -Name $name -Value $value -PropertyType DWORD -Force | Out-Null
	}
    
     else {
    
        New-ItemProperty -Path $registryPath -Name $name -Value $value -PropertyType DWORD -Force | Out-Null
	}
}
		
function main($url, $masters) {
    LongPathsSupport
    SetupDirectories
    SetupPathJson "C:\d2iq\dcos\etc\paths.json"

    Write-Log("Downloading/Extracting prerequisites.zip out of Bootstrap agent ...")
    Download "$url/windows/prerequisites/prerequisites.zip" "prerequisites.zip"
    $zipfile = "$($basedir)\bootstrap\prerequisites.zip"
    ExtractBootstrapZip $zipfile "$($basedir)\bootstrap\prerequisites"

    Write-Log("Installing 7zip from prerequisites.zip ...")
    & cmd /c "start /wait $($basedir)\bootstrap\prerequisites\7z-x64.exe /S" 2>&1 | Out-File "$($vardir)\log\dcos_install.log" -Append;

	Write-Log("Checking proper versions from latest.package_list.json ...")
	Download "$url/windows/package_lists/latest.package_list.json" "latest.package_list.json"
	$package_list_json = "$($basedir)\bootstrap\latest.package_list.json"
	echo $(cat $package_list_json | ConvertFrom-Json) | Where-Object { $_ -Match "python"} | New-Variable -Name python_package
	echo $(cat $package_list_json | ConvertFrom-Json) | Where-Object { $_ -Match "winpanda"} | New-Variable -Name winpanda_package

	Write-Log("Installing Python from Bootstrap agent - $($python_package).tar.xz...")
    Download "$url/windows/packages/python/$($python_package).tar.xz" "python.tar.xz"
    $pythontarfile = "$($basedir)\bootstrap\python.tar.xz"
    ExtractTarXz $pythontarfile "C:\python36"
	Add-EnvPath "C:\python36" "Session";
	Add-EnvPath "C:\python36" "Machine";

    Write-Log("Installing Winpanda from Bootstrap agent - $($winpanda_package).tar.xz ...")
    Download "$url/windows/packages/winpanda/$($winpanda_package).tar.xz" "winpanda.tar.xz"
    $winpandatarfile = "$($basedir)\bootstrap\winpanda.tar.xz"
    ExtractTarXz $winpandatarfile "$($basedir)"
	[Environment]::SetEnvironmentVariable("PYTHONPATH", "$($basedir)\winpanda\lib\python36\site-packages", [System.EnvironmentVariableTarget]::Machine);
	$env:PYTHONPATH="$($basedir)\winpanda\lib\python36\site-packages";

    Write-Log("Downloading ip-detect scripts from Bootstrap agent ...")
    Download "$url/windows/ip-detect.ps1" "detect_ip.ps1"
    Download "$url/windows/ip-detect-public.ps1" "detect_ip_public.ps1"
    Download "$url/windows/fault-domain-detect-win.ps1" "fault-domain-detect-win.ps1"
    Copy-Item -Path "$($basedir)\bootstrap\*.ps1" -Destination "$($basedir)\bin" -Recurse

    # Fill up Ansible inventory content to cluster.conf
    Write-Log("MASTERS: $($masters)")
    [System.Array]$masterarray = $masters.split(",")
    $masternodecontent = ""
    for ($i=0; $i -lt $masterarray.length; $i++) {
        $masternodecontent += "[master-node-$($i+1)]`nPrivateIPAddr=$($masterarray[$i])`nZookeeperListenerPort=2181`n"
    }
    $local_ip = (Get-WmiObject -Class Win32_NetworkAdapterConfiguration | where {$_.DefaultIPGateway -ne $null}).IPAddress | select-object -first 1
    Write-Log("Local IP: $($local_ip)")
    $content = "$($masternodecontent)`n[distribution-storage]`nRootUrl=$($url)`nPkgRepoPath=windows/packages`nPkgListPath=windows/package_lists/latest.package_list.json`nDcosClusterPkgInfoPath=cluster-package-info.json`n`n[local]`nPrivateIPAddr=$($local_ip)"
    CreateWriteFile "$($basedir)\etc" "cluster.conf" $content

    Write-Log("Running Winpanda.py setup ...")
    & python.exe "$($basedir)\winpanda\bin\winpanda.py" --inst-root-dir="$($basedir)" setup | Out-File "$($vardir)\log\dcos_install.log" -Append;
    if ($LASTEXITCODE -ne 0) {
        Write-Log("ERROR: command `'& python.exe `"$($basedir)\winpanda\bin\winpanda.py`" --inst-root-dir=`"$($basedir)`" setup`' failed, please check the winpanda.log");
		exit 1
    }
    Write-Log("Running Winpanda.py start ...")
    & python.exe "$($basedir)\winpanda\bin\winpanda.py" --inst-root-dir="$($basedir)" start | Out-File "$($vardir)\log\dcos_install.log" -Append;
    if ($LASTEXITCODE -ne 0) {
        Write-Log("ERROR: command `'& python.exe `"$($basedir)\winpanda\bin\winpanda.py`" --inst-root-dir=`"$($basedir)`" start`' failed, please check the winpanda.log");
		exit 1
    }
}

main $bootstrap_url $masters
