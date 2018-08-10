# This file mimics the behaviour on Linux by setting the dns
# lookup addresses on all adapters based on a set of rules:
#
# Always add addresses from $env:SEARCH to the SuffixSearchList
# If we can resolve name ready.spartan against dcos-net name server
# add those addresses otherwise add addresses from $env:RESOLVERS

$ErrorActionPreference = "Stop"

function Set-DcosInterfacesMetrics {
    $mainInterfaceIndex = (Get-NetRoute -DestinationPrefix "0.0.0.0/0").InterfaceIndex
    $dcosNetIntefaceAlias = "dcos-net"
    Set-NetIPInterface -InterfaceAlias $dcosNetIntefaceAlias -InterfaceMetric 1
    Set-NetIPInterface -InterfaceIndex $mainInterfaceIndex -InterfaceMetric 2
}

function Set-DefaultInterfacesMetrics {
    $stateFile = Join-Path $env:SystemDrive "opt\mesosphere\etc\interfaces_metrics_initial_state.json"
    if(!(Test-Path $stateFile)) {
        Write-Output "The interfaces metrics state file was not found: $stateFile"
        return
    }
    $state = Get-Content $stateFile | ConvertFrom-Json
    foreach($nic in $state) {
        Set-NetIPInterface -ifIndex $nic.ifIndex -AddressFamily $nic.AddressFamily `
                           -InterfaceAlias $nic.InterfaceAlias -InterfaceMetric $nic.InterfaceMetric
    }
}

$DCOS_NET_SERVERS = @('198.51.100.1', '198.51.100.2', '198.51.100.3')
$DNS_TEST_QUERY = 'ready.spartan'


$dnsSearchList = @()
if($env:SEARCH) {
    $dnsSearchList = $env:SEARCH.Split()
}
Set-DnsClientGlobalSetting -SuffixSearchList $dnsSearchList

$dcosNetServersUp = @()
foreach($dnsServer in $DCOS_NET_SERVERS) {
    try {
        Resolve-DnsName -Name $DNS_TEST_QUERY -Server $dnsServer -ErrorAction Stop
        # if successful add it to the list
        $dcosNetServersUp += $dnsServer
    } catch {
        Write-Output "Cannot resolve $DNS_TEST_QUERY using $dnsServer"
        Write-Output $_.ToString()
    }
}

$activeDnsServers = @()
if ($dcosNetServersUp.count -ne 0) {
    # Got some successes so add to list
    $activeDnsServers = $dcosNetServersUp
    # Set proper interfaces metrics for DC/OS
    Set-DcosInterfacesMetrics
} else {
    # If we did not get any of our name servers add
    # the resolvers instead
    $activeDnsServers = $env:RESOLVERS.Split(",")
    # Restore the original default interfaces metrics
    Set-DefaultInterfacesMetrics
}

Set-DnsClientServerAddress -InterfaceAlias * -ServerAddresses $activeDnsServers
