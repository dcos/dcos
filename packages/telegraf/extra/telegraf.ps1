 param (
    [string]$pkg_inst_dpath,
    [string]$dcos_conf_dpath,
    [string]$dcos_bin_dpath
 )

$IPAddress = ([System.Net.Dns]::GetHostByName("master.mesos").AddressList[0]).IpAddressToString
$local_ip = (Find-NetRoute -RemoteIPAddress $IPAddress | Select-Object  Ipv4Address).Ipv4Address[0]

[Environment]::SetEnvironmentVariable("DCOS_NODE_PRIVATE_IP",$local_ip, [System.EnvironmentVariableTarget]::Machine);
$env:DCOS_NODE_PRIVATE_IP=$local_ip;

& $pkg_inst_dpath\bin\telegraf.exe --config $dcos_conf_dpath\telegraf\telegraf.conf --service install
Start-Service -Name telegraf
