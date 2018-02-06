#
#
#
#[void]$global:script_path # A declaration

# Spartan configurations

$global:SPARTAN_SERVICE_NAME = "dcos-spartan"
$global:SPARTAN_DEVICE_NAME = "spartan"
$global:SPARTAN_DIR = Join-Path $DCOS_DIR "spartan"
$global:SPARTAN_RELEASE_DIR = Join-Path $global:SPARTAN_DIR "release"
$global:SPARTAN_LOG_DIR = Join-Path $global:SPARTAN_DIR "log"
$global:SPARTAN_SERVICE_DIR = Join-Path $global:SPARTAN_DIR "service"
$global:SPARTAN_GIT_REPO_DIR = Join-Path $global:SPARTAN_DIR "spartan"
$global:SPARTAN_BUILD_OUT_DIR = Join-Path $global:SPARTAN_DIR "build-output"
$global:SPARTAN_BUILD_LOGS_DIR = Join-Path $global:SPARTAN_BUILD_OUT_DIR "logs"
$global:SPARTAN_BUILD_BASE_URL = "$LOG_SERVER_BASE_URL/spartan-build"


#$TEMPLATES_DIR = Join-Path $PSScriptRoot "templates"
$global:SPARTAN_LATEST_RELEASE_URL = "$global:SPARTAN_BUILD_BASE_URL/master/latest/release.zip"


function New-Environment {
    $service = Get-Service $global:SPARTAN_SERVICE_NAME -ErrorAction SilentlyContinue
    if($service) {
        Stop-Service -Force -Name $global:SPARTAN_SERVICE_NAME

        $LASTEXITCODE = ""
        $res = Invoke-Command -ScriptBlock  { sc.exe delete $global:SPARTAN_SERVICE_NAME }
        if ($LASTEXITCODE) {
            if(!$ErrorMessage){
                Throw ("Command exited with status: {0}" -f $LASTEXITCODE)
            }
            Throw ("{0} (Exit code: $LASTEXITCODE)" -f "Failed to delete exiting EPMD service")
        }

    }
    New-Directory -RemoveExisting $global:SPARTAN_DIR
    New-Directory $global:SPARTAN_RELEASE_DIR
    New-Directory $global:SPARTAN_SERVICE_DIR
    New-Directory $global:SPARTAN_LOG_DIR
    $spartanReleaseZip = Join-Path $env:TEMP "spartan-release.zip"
    Write-Output "Downloading latest Spartan build"
    Invoke-WebRequest -UseBasicParsing -Uri $global:SPARTAN_LATEST_RELEASE_URL -OutFile $spartanReleaseZip
    Write-Output "Extracting Spartan zip archive to $global:SPARTAN_RELEASE_DIR"
    Expand-Archive -LiteralPath $spartanReleaseZip -DestinationPath $global:SPARTAN_RELEASE_DIR
    Remove-Item $spartanReleaseZip
}

function New-DevConBinary {
    $devConDir = Join-Path $env:TEMP "devcon"
    if(Test-Path $devConDir) {
        Remove-Item -Recurse -Force $devConDir
    }
    New-Item -ItemType Directory -Path $devConDir | Out-Null
    $devConCab = Join-Path $devConDir "devcon.cab"
    Invoke-WebRequest -UseBasicParsing -Uri $DEVCON_CAB_URL -OutFile $devConCab | Out-Null
    $devConFile = "filbad6e2cce5ebc45a401e19c613d0a28f"
    $LASTEXITCODE = ""
    $res = Invoke-Command -ScriptBlock { expand.exe $devConCab -F:$devConFile $devConDir } 
    if ($LASTEXITCODE) {
        if(!$ErrorMessage){
            Throw ("Command expand $devConCab exited with status: {0}" -f $LASTEXITCODE)
        }
        Throw ("{0} (Exit code: $LASTEXITCODE)" -f "Failed to expand $devConCab")
    }
    $devConBinary = Join-Path $env:TEMP "devcon.exe"
    Move-Item "$devConDir\$devConFile" $devConBinary
    Remove-Item -Recurse -Force $devConDir
    return $devConBinary
}

function Install-SpartanDevice {
    $spartanDevice = Get-NetAdapter -Name $global:SPARTAN_DEVICE_NAME -ErrorAction SilentlyContinue
    if($spartanDevice) {
        return
    }
    $devCon = New-DevConBinary
    Write-Output "Creating the Spartan network device"
    $res = Invoke-Command -ScriptBlock { & $devCon install "${env:windir}\Inf\Netloop.inf" "*MSLOOP" } 
    if ($LASTEXITCODE) {
        if(!$ErrorMessage){
            Throw ("Command expand $devConCab exited with status: {0}" -f $LASTEXITCODE)
        }
        Throw ("{0} (Exit code: $LASTEXITCODE)" -f "Failed to install the Spartan dummy interface")
    }
    $devConBinary = Join-Path $env:TEMP "devcon.exe"
    Remove-Item $devCon
    Get-NetAdapter | Where-Object { $_.DriverDescription -eq "Microsoft KM-TEST Loopback Adapter" } | Rename-NetAdapter -NewName $global:SPARTAN_DEVICE_NAME
}

function Set-SpartanDevice {
    $spartanDevice = Get-NetAdapter -Name $global:SPARTAN_DEVICE_NAME -ErrorAction SilentlyContinue
    if(!$spartanDevice) {
        Throw "Spartan network device was not found"
    }
    $spartanIPs = @("192.51.100.1", "192.51.100.2", "192.51.100.3")
    foreach($ip in $spartanIPs) {
        $address = Get-NetIPAddress -InterfaceAlias $global:SPARTAN_DEVICE_NAME -AddressFamily "IPv4" -IPAddress $ip -ErrorAction SilentlyContinue
        if($address) {
            continue
        }
        New-NetIPAddress -InterfaceAlias $global:SPARTAN_DEVICE_NAME -AddressFamily "IPv4" -IPAddress $ip -PrefixLength 32 | Out-Null
    }
    Disable-NetAdapter $global:SPARTAN_DEVICE_NAME -Confirm:$false
    Enable-NetAdapter $global:SPARTAN_DEVICE_NAME -Confirm:$false
}

function Get-UpstreamDNSResolvers {
    <#
    .SYNOPSIS
    Returns the DNS resolver(s) configured on the main interface
    #>
    $mainAddress = Get-NetIPAddress -AddressFamily IPv4 | Where-Object { $_.IPAddress -eq $AgentPrivateIP }
    if(!$mainAddress) {
        Throw "Could not find any NetIPAddress configured with the IP: $AgentPrivateIP"
    }
    $mainInterfaceIndex = $mainAddress.InterfaceIndex
    return (Get-DnsClientServerAddress -InterfaceIndex $mainInterfaceIndex).ServerAddresses
}

function New-SpartanWindowsAgent {
    $erlBinary = Join-Path $ERTS_DIR "bin\erl.exe"
    if(!(Test-Path $erlBinary)) {
        Throw "The erl binary $erlBinary doesn't exist. Cannot configure the Spartan agent Windows service"
    }
    $upstreamDNSResolvers = Get-UpstreamDNSResolvers | ForEach-Object { "{{" + ($_.Split('.') -join ', ') + "}, 53}" }
    $dnsZonesFile = "${SPARTAN_RELEASE_DIR}\spartan\data\zones.json" -replace '\\', '\\'
    # TODO(ibalutoiu): Instead of taking one of the masters' addresses for the exhibitor URL, we might
    #                  add an internal load balancer and use that address for the exhibitor URL.
    $exhibitorURL = "http://$($MasterAddress[0]):${EXHIBITOR_PORT}/exhibitor/v1/cluster/status"
    $context = @{
        "exhibitor_url" = $exhibitorURL
        "dns_zones_file" = $dnsZonesFile
        "upstream_resolvers" = "[$($upstreamDNSResolvers -join ', ')]"
    }
    $spartanConfigFile = Join-Path $global:SPARTAN_DIR "sys.spartan.config"

    import-module "$ScriptPath/../templating/extra/Templating.psm1"
    . "$script_path/../templating/extra/Load-Assemblies.ps1"

    $content = Invoke-RenderTemplateFromFile -Context $context -Template "$ScriptPath/extra/sys.spartan.config" 
    try {
        [System.IO.File]::WriteAllText("$global:SPARTAN_DIR\sys.spartan.config", $content)
    } 
    catch {
        Write-Output "could not write file"
        throw $_
    }
    $spartanVMArgsFile = Join-Path $global:SPARTAN_DIR "vm.spartan.args"
    $context = @{
        "agent_private_ip" = $AgentPrivateIP
        "epmd_port" = $global:EPMD_PORT
    }
    $content = Invoke-RenderTemplateFromFile -Context $context -Template "$ScriptPath/extra/vm.spartan.args"
    try {
        [System.IO.File]::WriteAllText("$global:SPARTAN_DIR\vm.spartan.args", $content)
    } 
    catch {
        Write-Output "could not write file"
        throw $_
    }
    $spartanArguments = ("-noshell -noinput +Bd -mode embedded " + `
                         "-rootdir `"${SPARTAN_RELEASE_DIR}\spartan`" " + `
                         "-boot `"${SPARTAN_RELEASE_DIR}\spartan\releases\0.0.1\spartan`" " + `
                         "-boot_var ERTS_LIB_DIR `"${SPARTAN_RELEASE_DIR}\lib`" " + `
                         "-boot_var RELEASE_DIR `"${SPARTAN_RELEASE_DIR}\spartan`" " + `
                         "-config `"${spartanConfigFile}`" " + `
                         "-args_file `"${spartanVMArgsFile}`" -pa " + `
                         "-- foreground")
    $context = @{
        "service_name" = $global:SPARTAN_SERVICE_NAME
        "service_display_name" = "Spartan Windows Agent"
        "service_description" = "Windows Service for the DCOS Spartan Windows Agent"
        "service_binary" = $erlBinary
        "service_arguments" = $spartanArguments
        "log_dir" = $global:SPARTAN_LOG_DIR
    }
    $env:MASTER_SOURCE = "exhibitor"
    $LASTEXITCODE = ""
    $res = Invoke-Command -ScriptBlock { setx.exe /M MASTER_SOURCE "exhibitor" }
    if ($LASTEXITCODE) {
        if(!$ErrorMessage){
            Throw ("Command exited with status: {0}" -f $LASTEXITCODE)
        }
        Throw ("{0} (Exit code: $LASTEXITCODE)" -f  "Failed to set the Spartan MASTER_SOURCE system environment variable" )
    }

    $env:EXHIBITOR_ADDRESS = $MasterAddress[0]
    $LASTEXITCODE = ""
    $res = Invoke-Command -ScriptBlock { setx.exe /M EXHIBITOR_ADDRESS $MasterAddress[0] }
    if ($LASTEXITCODE) {
        if(!$ErrorMessage){
            Throw ("Command exited with status: {0}" -f $LASTEXITCODE)
        }
        Throw ("{0} (Exit code: $LASTEXITCODE)" -f "Failed to set the Spartan EXHIBITOR_ADDRESS system environment variable" )
    }

    $content = Invoke-RenderTemplateFromFile -Context $context -Template "$ScriptPath/../WinSW/extra/windows-service.xml" 
    try {
        [System.IO.File]::WriteAllText("$global:SPARTAN_SERVICE_DIR\spartan-service.xml", $content)
    } 
    catch {
        Write-Output "could not write file"
        throw $_
    }
    $serviceWapper = Join-Path $global:SPARTAN_SERVICE_DIR "spartan-service.exe"
    Invoke-WebRequest -UseBasicParsing -Uri $SERVICE_WRAPPER_URL -OutFile $serviceWapper
    $p = Start-Process -FilePath $serviceWapper -ArgumentList @("install") -NoNewWindow -PassThru -Wait
    if($p.ExitCode -ne 0) {
        Throw "Failed to set up the Spartan Windows service. Exit code: $($p.ExitCode)"
    }
    # Temporary stop Docker service because we have port 53 bound and this needs to be used by Spartan
    # TODO(ibalutoiu): Permanently disable the Docker embedded DNS and remove this workaround
    Stop-Service "Docker"

    Start-Service $global:SPARTAN_SERVICE_NAME

    # Check to verify the service is actually running before we return. If the service is not up in 20 seconds, throw an exception
    $timeout = 2
    $count = 0
    $maxCount = 10
    while ($count -lt $maxCount) {
        Start-Sleep -Seconds $timeout
        Write-Output "Checking $global:SPARTAN_SERVICE_NAME service status"
        $status = (Get-Service -Name $global:SPARTAN_SERVICE_NAME).Status
        if($status -ne [System.ServiceProcess.ServiceControllerStatus]::Running) {
            Throw "Service $global:SPARTAN_SERVICE_NAME is not running"
        }
        $count++
    }

    # Point the DNS from the host to the Spartan local DNS
    Set-DnsClientServerAddress -InterfaceAlias * -ServerAddresses @('192.51.100.1', '192.51.100.2', '192.51.100.3')

    # TODO(ibalutoiu): Remove this workaround of stopping/starting the Docker service once the embedded Docker DNS is disabled
    Start-Service "Docker"
}


class Spartan:Installable
{
    static [string] $ClassName = "Spartan"
    [string] Setup( [string] $script_path,
           [string[]]$MasterAddress,
           [string]$AgentPrivateIP,
           [switch]$Public=$false
         ) { 
        Write-Host "Setup Spartan : $script_path";
        $UDP_RULE_NAME = "Allow inbound UDP Port 53 for Spartan"
        $TCP_RULE_NAME = "Allow inbound TCP Port 53 for Spartan"

        Write-Host "service name = $global:SPARTAN_SERVICE_NAME"
        try {
            New-Environment
            Install-SpartanDevice
            Set-SpartanDevice
            New-SpartanWindowsAgent

            Write-Output "Open firewall rule: $TCP_RULE_NAME"
            $firewallRule = Get-NetFirewallRule -DisplayName $TCP_RULE_NAME -ErrorAction SilentlyContinue
            if($firewallRule) {
                Write-Output "Firewall rule $TCP_RULE_NAME already exists. Skipping"
            }
            else 
            {
                New-NetFirewallRule -DisplayName $TCP_RULE_NAME -Direction "Inbound" -LocalPort 53 -Protocol "TCP" -Action Allow | Out-Null
            }

            Write-Output "Open firewall rule: $UDP_RULE_NAME"
            $firewallRule = Get-NetFirewallRule -DisplayName $UDP_RULE_NAME -ErrorAction SilentlyContinue
            if($firewallRule) {
                Write-Output "Firewall rule $UDP_RULE_NAME already exists. Skipping"
            }
            else 
            {
                New-NetFirewallRule -DisplayName $UDP_RULE_NAME -Direction "Inbound" -LocalPort 53 -Protocol "UDP" -Action Allow | Out-Null
            }

        } catch {
            throw $_
        }
        Write-Output "Successfully finished setting up the Windows Spartan Agent"
        return $true
    }
}



