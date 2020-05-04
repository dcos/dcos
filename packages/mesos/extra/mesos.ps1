param (
    [string]$path_to_dcos_bin = "c:\d2iq\dcos\bin",
    [string]$path_to_dcos_conf = "c:\d2iq\dcos\etc\mesos"
    )

$domain = & $path_to_dcos_bin\fault-domain-detect-win.ps1
Set-Content $path_to_dcos_conf\domain.json $domain -Force

& $path_to_dcos_bin\bootstrap.ps1 dcos-mesos-slave
