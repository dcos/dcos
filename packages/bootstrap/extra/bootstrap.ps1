 param (
    [string]$pkg_inst_dpath
 )

## Get installation directory path and var directory path from C:\d2iq\dcos\etc\paths.json.
## The location of paths.json file is predifined and shouldn't be changed.

$json = Get-Content 'C:\d2iq\dcos\etc\paths.json' | Out-String | ConvertFrom-Json
$install_dir = $json.install
$var_dir = $json.var
$Env:PYTHONPATH = "$pkg_inst_dpath\lib\python36\site-packages;$pkg_inst_dpath"

& python "$pkg_inst_dpath\bin\bootstrap"  dcos-adminrouter-agent --zk_agent_creds "$install_dir\etc\zk_agent_credentials" --config-path "$install_dir\etc\bootstrap-config.json"