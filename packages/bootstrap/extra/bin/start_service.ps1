<#
 D2IQ DC/OS - universal service startup powershell script for Windows OS
#>

param (
  [string] [Parameter(Mandatory = $true, Position = 0)] $prescript,
  [string] [Parameter(Mandatory = $true, Position = 1)] $precommand,
  [string] [Parameter(Mandatory = $true, Position = 2)] $application,
  [string[]] [Parameter(Position=3, ValueFromRemainingArguments)] $command
)

$ErrorActionPreference = "stop"

[string]$powershell = (Get-Command powershell).Source
# ExecPre for pre-sripts: bootstrap.ps1, etc
[string]$ExecStartPre = '{0} -ExecutionPolicy Bypass -NoProfile -File "{1}" "{2}"' -f "$powershell", "$prescript", "$precommand"
# ExecStart for actual binary execution : mesos.exe, telegraf.exe, etc:
[string]$ExecStart = "$application $command"

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
    cmd /c $ExecStartPre '2>&1'
}

# Execute start of the service:
Invoke-NativeApplication {
    cmd /c $ExecStart '2>&1'
}