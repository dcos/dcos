# Import full Windows PowerShell modules that we need. These three work fine
# with powershell core, although we cannot use the full DnsClient as that has
# dependencies we do not have, but the subset is all we need.

$ErrorActionPreference = "Stop"

Import-Module "${env:windir}\System32\WindowsPowerShell\v1.0\Modules\NetTCPIP\NetTCPIP.psd1"
Import-Module "${env:windir}\System32\WindowsPowerShell\v1.0\Modules\NetAdapter\NetAdapter.psd1"
Import-Module "${env:windir}\System32\WindowsPowerShell\v1.0\Modules\DnsClient\MSFT_DnsClientServerAddress.cdxml"

$DEVCON_CAB_URL = "https://download.microsoft.com/download/7/D/D/7DD48DE6-8BDA-47C0-854A-539A800FAA90/wdk/Installers/787bee96dbd26371076b37b13c405890.cab"
$LOOPBACK_ADAPTER_NAME = "dcos-net"
$LOOPBACK_ADAPTER_IPV4_ADDRESSES = @("198.51.100.1", "198.51.100.2", "198.51.100.3")
$INTERFACES_METRICS_STATE_FILE = Join-Path $env:SystemDrive "opt\mesosphere\etc\interfaces_metrics_initial_state.json"
$DCOS_NET_ACTIVE_DIR = Join-Path $env:SystemDrive "opt\mesosphere\active\dcos-net"


function Start-ExecuteWithRetry {
    Param(
        [Parameter(Mandatory=$true)]
        [ScriptBlock]$ScriptBlock,
        [int]$MaxRetryCount=10,
        [int]$RetryInterval=3,
        [string]$RetryMessage,
        [array]$ArgumentList=@()
    )
    $currentErrorActionPreference = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    $retryCount = 0
    while ($true) {
        try {
            $res = Invoke-Command -ScriptBlock $ScriptBlock `
                                  -ArgumentList $ArgumentList
            $ErrorActionPreference = $currentErrorActionPreference
            return $res
        } catch [System.Exception] {
            $retryCount++
            if ($retryCount -gt $MaxRetryCount) {
                $ErrorActionPreference = $currentErrorActionPreference
                Throw
            } else {
                if($RetryMessage) {
                    Write-Output $RetryMessage
                } elseif($_) {
                    Write-Output $_.ToString()
                }
                Start-Sleep $RetryInterval
            }
        }
    }
}

function Start-FileDownloadWithCurl {
    Param(
        [Parameter(Mandatory=$true)]
        [string]$URL,
        [Parameter(Mandatory=$true)]
        [string]$Destination,
        [Parameter(Mandatory=$false)]
        [int]$RetryCount=10
    )
    $params = @('-fLsS', '-o', "`"${Destination}`"", "`"${URL}`"")
    Start-ExecuteWithRetry -ScriptBlock {
        $p = Start-Process -FilePath 'curl.exe' -NoNewWindow -ArgumentList $params -Wait -PassThru
        if($p.ExitCode -ne 0) {
            Throw "Fail to download $URL"
        }
    } -MaxRetryCount $RetryCount -RetryInterval 3 -RetryMessage "Failed to download ${URL}. Retrying"
}

function New-LoopbackAdapter {
    # First check to see if it is already installed
    $dcosNetDevice = Get-NetAdapter -Name $LOOPBACK_ADAPTER_NAME -ErrorAction SilentlyContinue
    if ($dcosNetDevice) {
        # Already there
        Write-Output "The loopback adapter $LOOPBACK_ADAPTER_NAME already exists"
        return
    }
    $devconCab = Join-Path $env:TEMP "devcon.cab"
    Start-FileDownloadWithCurl -URL $DEVCON_CAB_URL -Destination $devconCab -RetryCount 30
    $devConFileName = "filbad6e2cce5ebc45a401e19c613d0a28f"
    expand.exe $devconCab -F:$devConFileName $env:TEMP
    if($LASTEXITCODE) {
        Throw "Failed to expand DevCon cab file"
    }
    $devConFile = Join-Path $env:TEMP $devConFileName
    $devConBinary = Join-Path $env:TEMP "devcon.exe"
    Move-Item $devConFile $devConBinary
    Remove-Item -Force $devconCab
    # Create the dcos-net loopback adapter
    & $devConBinary install "${env:windir}\Inf\Netloop.inf" "*MSLOOP"
    if($LASTEXITCODE -ne 0) {
        throw "Failed to run devcon.exe to install the dcos-net loopback network adapter"
    }
    Remove-Item -Force $devConBinary
    Get-NetAdapter | Where-Object { $_.DriverDescription -eq "Microsoft KM-TEST Loopback Adapter" } | Rename-NetAdapter -NewName $LOOPBACK_ADAPTER_NAME
}

function Set-LoopbackAdapterAddresses {
    # Get the adapter. It should exist before calling this.
    $dcosNetDevice = Get-NetAdapter -Name $LOOPBACK_ADAPTER_NAME -ErrorAction SilentlyContinue
    if(!$dcosNetDevice) {
        Throw "$LOOPBACK_ADAPTER_NAME adapter was not found"
    }
    foreach($address in $LOOPBACK_ADAPTER_IPV4_ADDRESSES) {
        # Check if address already exists, if so we don't need to do anything
        $existingAddress = Get-NetIPAddress -InterfaceAlias $LOOPBACK_ADAPTER_NAME -AddressFamily "IPv4" -IPAddress $address -ErrorAction SilentlyContinue
        if($existingAddress) {
            continue
        }
        # Not currently there, so we add address to the adapter
        New-NetIPAddress -InterfaceAlias $LOOPBACK_ADAPTER_NAME -AddressFamily "IPv4" -IPAddress $address -PrefixLength 32
    }
    Set-DnsClientServerAddress -InterfaceAlias * -ServerAddresses $LOOPBACK_ADAPTER_IPV4_ADDRESSES
}

function Set-InteracesMetrics {
    if(Test-Path $INTERFACES_METRICS_STATE_FILE) {
        Write-Output "The interfaces metrics state file already exists: $INTERFACES_METRICS_STATE_FILE"
        return
    }
    # Save the interfaces metrics state and set a lower metrics for the dcos-net interface
    $mainInterfaceIndex = (Get-NetRoute -DestinationPrefix "0.0.0.0/0").InterfaceIndex
    $state = @()
    Get-NetIPInterface | ForEach-Object {
        if($_.ifIndex -eq $mainInterfaceIndex -or $_.InterfaceAlias -eq $args[1]) {
            $state += @{
                "ifIndex" = $_.ifIndex
                "InterfaceAlias" = $_.InterfaceAlias
                "AddressFamily" = $_.AddressFamily
                "InterfaceMetric" = $_.InterfaceMetric
            }
        }
    }
    $state | ConvertTo-Json | Out-File -PSPath $INTERFACES_METRICS_STATE_FILE -Encoding ascii
    Set-NetIPInterface -InterfaceAlias $LOOPBACK_ADAPTER_NAME -InterfaceMetric 1
    Set-NetIPInterface -InterfaceIndex $mainInterfaceIndex -InterfaceMetric 2
}

function New-DcosNetSysConfigFile {
    $sysConfig = Join-Path $env:SystemDrive "opt\mesosphere\etc\sys.config"
    if(Test-Path $sysConfig) {
        # Already exists
        Write-Output "The sys.config file already exists: $sysConfig"
        return
    }
    $sysConfigWin = Join-Path $env:SystemDrive "opt\mesosphere\etc\sys.config.windows"
    if(!(Test-Path $sysConfigWin)) {
        Throw "The sys.config template file for Windows doesn't exist: $sysConfigWin"
    }
    if(!$env:RESOLVERS) {
        Throw "The environment variable RESOLVERS is not set"
    }
    $upstreamDNSResolvers = $env:RESOLVERS -split ',' | ForEach-Object { "{{" + ($_.Split('.') -join ', ') + "}, 53}" }
    $strUpstreamDNSResolvers = $upstreamDNSResolvers -join ', '
    $sysConfigContent = Get-Content $sysConfigWin | ForEach-Object { $_ -replace 'DCOS_NET_UPSTREAM_RESOLVERS', $strUpstreamDNSResolvers }
    Set-Content -Path $sysConfig -Value $sysConfigContent -Encoding ascii
}

function New-DcosNetVmArgsFile {
    $vmargs = Join-Path $env:SystemDrive "opt\mesosphere\etc\vm.args"
    if(Test-Path $vmargs) {
        Write-Output "The vm.args file already exists: $vmargs"
        return
    }
    $vmargsWin = Join-Path $env:SystemDrive "opt\mesosphere\etc\vm.args.windows"
    if(!(Test-Path $vmargsWin)) {
        Throw "The dcos-net vm.args template file for Windows doesn't exist: $vmargsWin"
    }
    $detectIPScript = Join-Path $env:SystemDrive "opt\mesosphere\bin\detect_ip.ps1"
    if(!(Test-Path $detectIPScript)) {
        Throw "The detect_ip.ps1 script doesn't exist: $detectIPScript"
    }
    $privateIP = pwsh.exe -File "$detectIPScript"
    if($LASTEXITCODE) {
        Throw "Failed to get the private IP with the script: $detectIPScript"
    }
    $vmargsContent = Get-Content $vmargsWin | ForEach-Object { $_ -replace 'DCOS_AGENT_PRIVATE_IP', $privateIP }
    Set-Content -Path $vmargs -Value $vmargsContent -Encoding ascii
}

function New-ErlIniFile {
    $erlIniFile = Join-Path $DCOS_NET_ACTIVE_DIR "dcos-net\erts-10.1\bin\erl.ini"
    $binDir = "${DCOS_NET_ACTIVE_DIR}\dcos-net\erts-10.1\bin" -replace '\\', '/'
    $rootDir = "${DCOS_NET_ACTIVE_DIR}\dcos-net" -replace '\\', '/'
    $erlIniContent = @(
        "[erlang]",
        "Bindir=${binDir}",
        "Progname=erl",
        "Rootdir=${rootDir}"
    )
    Set-Content -Path $erlIniFile -Value $erlIniContent -Encoding ascii
}

function New-DcosNetConfigFiles {
    New-DcosNetSysConfigFile
    New-DcosNetVmArgsFile
    New-ErlIniFile
}


try {
    New-LoopbackAdapter
    Set-LoopbackAdapterAddresses
    Set-InteracesMetrics
    New-DcosNetConfigFiles
} catch {
    Write-Output $_.ToString()
    Write-Output $_.ScriptStackTrace
    exit 1
}
exit 0
