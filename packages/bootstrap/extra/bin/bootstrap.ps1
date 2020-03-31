param (
    [Parameter(Mandatory=$true)] [string] $service
)

$ErrorActionPreference = "stop"

function Test-CalledFromPrompt {
    (Get-PSCallStack)[-2].Command -eq "prompt"
}

function Invoke-NativeApplication {
    # The helper function is used to run Native Windows apps in PS1 such as python.exe or cmd.exe. IMPORTANT, it cannot be used to run PS1 CmdLets!
    # Source code: https://github.com/mnaoumov/Invoke-NativeApplication
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
            $lines = & $ScriptBlock
        }
        else {
            $lines = & $ScriptBlock 2>&1
        }
        $lines | ForEach-Object -Process `
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

$PKG_STORE = "c:\d2iq\dcos\lib\bootstrap"

$Env:PYTHONPATH = "$PKG_STORE"

Invoke-NativeApplication {
    python.exe -c 'from dcos_internal_utils.cli import main; main()' "$service"
}
