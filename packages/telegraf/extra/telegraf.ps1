 param (
    [string]$pkg_inst_dpath,
    [string]$dcos_conf_dpath
 )

$IPAddress = ([System.Net.Dns]::GetHostByName("master.mesos").AddressList[0]).IpAddressToString
$local_ip = (Find-NetRoute -RemoteIPAddress $IPAddress | Select-Object  Ipv4Address).Ipv4Address[0]

[Environment]::SetEnvironmentVariable("DCOS_NODE_PRIVATE_IP",$local_ip, [System.EnvironmentVariableTarget]::Machine);
$env:DCOS_NODE_PRIVATE_IP=$local_ip;

& $pkg_inst_dpath\bin\telegraf.exe --config $dcos_conf_dpath\telegraf\telegraf.conf --service install

function Set-ServiceRecovery{
    [alias('Set-Recovery')]
    param
    (
        [string] [Parameter(Mandatory=$true)] $ServiceDisplayName,
        [string] $action1 = "restart",
        [int] $time1 =  30000, 
        [string] $action2 = "restart",
        [int] $time2 =  30000,
        [string] $actionLast = "restart",
        [int] $timeLast = 30000, 
        [int] $resetCounter = 4000 
    )
    $services = Get-CimInstance -ClassName 'Win32_Service' | Where-Object {$_.DisplayName -imatch $ServiceDisplayName}
    $action = $action1+"/"+$time1+"/"+$action2+"/"+$time2+"/"+$actionLast+"/"+$timeLast
    foreach ($service in $services){
        $output = sc.exe $serverPath failure $($service.Name) actions= $action reset= $resetCounter
    }
}
Set-ServiceRecovery -ServiceDisplayName "Telegraf Data Collector Service"
Start-Service -Name telegraf
