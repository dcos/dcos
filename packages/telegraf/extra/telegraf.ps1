 param (
    [string]$pkg_inst_dpath,
    [string]$dcos_conf_dpath
 )

& $pkg_inst_dpath\bin\telegraf.exe --config $dcos_conf_dpath\telegraf\telegraf.conf --service install
Start-Service -Name telegraf
