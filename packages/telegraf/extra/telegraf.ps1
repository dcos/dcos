 param (
    [string]$pkg_inst_dpath,
    [string]$dcos_conf_dpath
 )

$IPAddress = ([System.Net.Dns]::GetHostByName("master.mesos").AddressList[0]).IpAddressToString
$local_ip = (Find-NetRoute -RemoteIPAddress $IPAddress | Select-Object  Ipv4Address).Ipv4Address[0]

[Environment]::SetEnvironmentVariable("DCOS_NODE_PRIVATE_IP",$local_ip, [System.EnvironmentVariableTarget]::Machine);
$env:DCOS_NODE_PRIVATE_IP=$local_ip;

& $pkg_inst_dpath\bin\telegraf.exe --config $dcos_conf_dpath\telegraf\telegraf.conf --service install

# set the Service Recovery options to "Restart the Service" every time the service crashes
function Set-ServiceRecovery{
    [alias('Set-Recovery')]
    param
    (
        [string] [Parameter(Mandatory=$true)] $ServiceDisplayName,
        [string] $action = "restart", 
        [int] $time =  30000, # in miliseconds
        [int] $resetCounter = 4000 # in seconds
    )
    $services = Get-CimInstance -ClassName 'Win32_Service' | Where-Object {$_.DisplayName -imatch $ServiceDisplayName}
    $action = $action+"/"+$time+"/"+$action+"/"+$time+"/"+$action+"/"+$time
    foreach ($service in $services){
        $output = sc.exe $serverPath failure $($service.Name) actions= $action reset= $resetCounter
    }
}
Set-ServiceRecovery -ServiceDisplayName "Telegraf Data Collector Service"
Start-Service -Name telegraf
