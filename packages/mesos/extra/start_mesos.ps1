<#
 D2IQ DC/OS - Mesos-Agent service startup ps1 script for Windows OS
#>

param (
  [string] [Parameter(Mandatory = $true, Position = 0)] $prescript1,
  [string] [Parameter(Mandatory = $true, Position = 1)] $precommand1,
  [string] [Parameter(Mandatory = $true, Position = 2)] $prescript2,
  [string] [Parameter(Mandatory = $true, Position = 3)] $precommand2,
  [string] [Parameter(Mandatory = $true, Position = 4)] $application,
  [string[]] [Parameter(Position=5, ValueFromRemainingArguments)] $command
)

$ErrorActionPreference = "stop"

[string]$powershell = (Get-Command powershell).Source
# ExecStartPre for pre-sripts: bootstrap.ps1, etc
[string]$ExecStartPre1 = '{0} -ExecutionPolicy Bypass -NoProfile -Command "$domain = & {1}; Set-Content {2} $domain -Force"' -f "$powershell", "$prescript1", "$precommand1"
Write-Host $ExecStartPre1
[string]$ExecStartPre2 = '{0} -ExecutionPolicy Bypass -NoProfile -File "{1}" "{2}"' -f "$powershell", "$prescript2", "$precommand2"
Write-Host $ExecStartPre2
# ExecStart for actual binary execution : mesos.exe, telegraf.exe, etc:
[string]$ExecStart = "$application $command"
Write-Host $ExecStart

### Helpers:
function Test-CalledFromPrompt {
    (Get-PSCallStack)[-2].Command -eq "prompt"
}

function Invoke-NativeApplication {
    param
    (
        [ScriptBlock] $ScriptBlock,
        [int[]] $AllowedExitCodes = @(0),
        [switch] $IgnoreExitCode
    )
    [string] $stringScriptBlock = $ScriptBlock.ToString();
    $backupErrorActionPreference = $ErrorActionPreference;
    $ErrorActionPreference = "Continue";
    try {
        if (Test-CalledFromPrompt) {
            $lines = { & $ScriptBlock }
        }
        else {
            $lines = { & $ScriptBlock 2>&1 }
        }
        & $lines | ForEach-Object -Process `
            {
                $isError = $_ -is [System.Management.Automation.ErrorRecord]
                "$_" | Add-Member -Name IsError -MemberType NoteProperty -Value $isError -PassThru
            }
        if ((-not $IgnoreExitCode) -and ($AllowedExitCodes -notcontains $LASTEXITCODE)) {
            throw "$(Get-Date -Format "yyyy-MM-dd HH:mm:ss") ERROR: Failed to execute `'$stringScriptBlock`' : returned $LASTEXITCODE. Check traceback for more details!" 2>&1
        }
    }
    finally {
        $ErrorActionPreference = $backupErrorActionPreference
    }
}

### Main execution:
# Execute pre command:
Invoke-NativeApplication {
    cmd /c $ExecStartPre1 '2>&1'
}
Invoke-NativeApplication {
    cmd /c $ExecStartPre2 '2>&1'
}

# Execute start of the service:
Invoke-NativeApplication {
    cmd /c $ExecStart '2>&1'
}