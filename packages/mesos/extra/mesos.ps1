param (
    [string]$path_to_packages = "c:\d2iq\dcos\packages",
    [string]$path_to_dcos_bin = "c:\d2iq\dcos\bin",
    [string]$path_to_dcos_conf = "c:\d2iq\dcos\etc\mesos"
    )

$domain = & $path_to_dcos_bin\fault-domain-detect-win.ps1
Set-Content $path_to_dcos_conf\domain.json $domain -Force

$packagebootsrapname = [string[]](Get-ChildItem $path_to_packages -Recurse -Filter bootstrap--*)
$pathtobootstrap = "$path_to_packages\$packagebootsrapname"

$Env:PYTHONPATH = "$pathtobootstrap\lib\python36\site-packages;$pathtobootstrap"

& python "$pathtobootstrap\bin\bootstrap" dcos-mesos-slave
