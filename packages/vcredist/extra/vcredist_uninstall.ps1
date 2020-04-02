#requires -version 4
<#
.SYNOPSIS
  Name: vcredist_uninstall.ps1
  Script for uninstalling of Microsoft Visual C++ Redistributable for Visual Studio 2015, 2017 and 2019 during upgrade of DC/OS on a Windows node. 
.DESCRIPTION
  The script will:
  - Check the file system and find all logical drives
  - Search recursively for file paths.json through the file system. The mentioned file is the source of truth of the installation path of DCOS.
  - Parse the file to find out the installation directory of DCOS.
  - Uninstall Microsoft Visual C++ Redistributable for Visual Studio 2015, 2017 and 2019.
  - Write an uninstallation log to logdir
.PARAMETER install_dir
  [Optional] DC/OS installation root directory. Default value is C:\d2iq\dcos

.PARAMETER var_dir
  [Optional] DC/OS variable directory for a files created by bootstrap process, for logs stored. Default value is C:\d2iq\dcos\var

.NOTES
  Version:        1.0
  Author:         Vadym Zagorodko
  Creation Date:  24.02.2020
  Purpose/Change: To manage the unistallation of vcredist package during update of DCOS cluster

.EXAMPLE
#  .\vcredist_uninstall.ps1 <install_dir> <var_dir>
#>

# PARAMETERS
param (
    [Parameter(Mandatory=$false)][string] $install_dir = 'C:\d2iq\dcos',
    [Parameter(Mandatory=$false)][string] $var_dir = 'C:\d2iq\dcos\var'
)

$ErrorActionPreference = "Stop"

#Logdir should be idempotent for each installation of DCOS. However, it can be changed via paramater if needed.  
$logdir = "$var_dir\log"

#At the moment, the path to the file paths.json is hardcoded under insatll_dir. 

$path_to_json ="$install_dir\etc\paths.json"

#However, if you're not sure where DCOS install_dir is located but need to find paths.json, please comment $path_to_json above and uncomment the section below.

#  #Get a list of logical drives
# $Drives = Get-PSDrive -PSProvider 'FileSystem'
# $path_to_json = foreach($Drive in $drives) {
#
#    #Find paths.json file in given directory
#   Get-ChildItem -Path $Drive.Root -Filter paths.json -Recurse -ErrorAction SilentlyContinue -Force | ForEach-Object{$_.FullName}
# }

$json = Get-Content $path_to_json | ConvertFrom-Json

#Set recognized installation directory as a variable
$basedir = $json.install

#Perform uninstallation and write a log to logdir
& $basedir\bin\install\vc_redist.x64.exe /uninstall /quiet /log $logdir\vcredist_uninstall.log