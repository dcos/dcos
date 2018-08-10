$ErrorActionPreference = "Stop"

Import-Module "${env:windir}\System32\WindowsPowerShell\v1.0\Modules\NetTCPIP\NetTCPIP.psd1"
Import-Module "${env:windir}\System32\WindowsPowerShell\v1.0\Modules\NetAdapter\NetAdapter.psd1"

$EXTRA_ENV_FILE = Join-Path $env:SystemDrive "var\lib\dcos\mesos-slave-common.ps1"


function Get-AgentPrivateIP {
    $primaryIfIndex = (Get-NetRoute -DestinationPrefix "0.0.0.0/0").ifIndex
    return (Get-NetIPAddress -AddressFamily IPv4 -ifIndex $primaryIfIndex).IPAddress
}

function Set-MesosIP {
    if(Test-Path $EXTRA_ENV_FILE) {
        [array]$content = Get-Content $EXTRA_ENV_FILE
    } else {
        [array]$content = @()
    }
    # Remove any MESOS_IP from the env file content
    [array]$newContent = $content | Where-Object { $_ -cnotmatch '\s*\$env\:MESOS_IP\s*\=' }
    # Append the updated MESOS_IP
    $newContent += "`$env:MESOS_IP=`"$(Get-AgentPrivateIP)`""
    # Make sure the parent directory exists
    New-Item -ItemType "Directory" -Force -Path (Split-Path -Parent -Path $EXTRA_ENV_FILE) > $null
    # Set the env file new content
    Set-Content -Path $EXTRA_ENV_FILE -Value $newContent -Encoding Ascii
}


try {
    Set-MesosIP
} catch {
    Write-Output $_.ScriptStackTrace
    exit 1
}
exit 0
