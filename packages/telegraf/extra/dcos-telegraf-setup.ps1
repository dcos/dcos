$ErrorActionPreference = "Stop"

$CLUSTER_ID_FILE = Join-Path $env:SystemDrive "var\lib\dcos\cluster-id"


function New-TelegrafConfigFile {
    $conf = Join-Path $env:SystemDrive "opt\mesosphere\etc\telegraf\telegraf.conf"
    $confWin = "${conf}.windows"
    if(!(Test-Path $confWin)) {
        Throw "The $confWin template file for Windows doesn't exist"
    }
    if(!(Test-Path $CLUSTER_ID_FILE)) {
        Throw "Cluster id file $CLUSTER_ID_FILE doesn't exist"
    }
    $clusterId = Get-Content $CLUSTER_ID_FILE
    $confContent = Get-Content $confWin | ForEach-Object { $_ -replace 'DCOS_CURRENT_CLUSTER_ID', $clusterId }
    Set-Content -Path $conf -Value $confContent -Encoding ascii
}

function New-TelegrafAgentConfigFile {
    $agentConf = Join-Path $env:SystemDrive "opt\mesosphere\etc\telegraf\telegraf.d\agent.conf"
    $agentConfWin = "${agentConf}.windows"
    if(!(Test-Path $agentConfWin)) {
        Throw "The $agentConfWin template file for Windows doesn't exist"
    }
    if(!(Test-Path $CLUSTER_ID_FILE)) {
        Throw "Cluster id file $CLUSTER_ID_FILE doesn't exist"
    }
    $clusterId = Get-Content $CLUSTER_ID_FILE
    $detectIPScript = Join-Path $env:SystemDrive "opt\mesosphere\bin\detect_ip.ps1"
    if(!(Test-Path $detectIPScript)) {
        Throw "The detect_ip.ps1 script doesn't exist: $detectIPScript"
    }
    $privateIP = pwsh.exe -File "$detectIPScript"
    if($LASTEXITCODE) {
        Throw "Failed to get the private IP with the script: $detectIPScript"
    }
    $agentConfContent = Get-Content $agentConfWin | ForEach-Object { $_ -replace 'DCOS_CURRENT_CLUSTER_ID', $clusterId } | `
                                                    ForEach-Object { $_ -replace 'DCOS_AGENT_PRIVATE_IP', $privateIP }
    Set-Content -Path $agentConf -Value $agentConfContent -Encoding ascii
}


try {
    New-TelegrafConfigFile
    New-TelegrafAgentConfigFile
} catch {
    Write-Output $_.ToString()
    Write-Output $_.ScriptStackTrace
    exit 1
}
exit 0
