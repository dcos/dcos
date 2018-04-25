$ErrorActionPreference = "stop"
# Mesos configurationsG
$MESOS_DIR = "c:\mesos-tmp"
$MESOS_BUILD_DIR = Join-Path $MESOS_DIR "build"
$MESOS_GIT_REPO_DIR = Join-Path $MESOS_DIR "mesos"
$MESOS_BUILD_OUT_DIR = Join-Path $MESOS_DIR "build-output"

function New-Directory {
    Param(
        [Parameter(Mandatory=$true)]
        [string]$Path,
        [Parameter(Mandatory=$false)]
        [switch]$RemoveExisting
    )
    if(Test-Path $Path) {
        if($RemoveExisting) {
            # Remove if it already exist
            Remove-Item -Recurse -Force $Path
        } else {
            return
        }
    }
    return (New-Item -ItemType Directory -Path $Path)
}

function New-Environment {
    Write-Output "Creating new tests environment"
    New-Directory $MESOS_BUILD_DIR
    New-Directory $MESOS_BUILD_OUT_DIR -RemoveExisting
    Write-Output "New tests environment was successfully created"
}

function Start-ExternalCommand {
    <#
    .SYNOPSIS
    Helper function to execute a script block and throw an exception in case of error.
    .PARAMETER ScriptBlock
    Script block to execute
    .PARAMETER ArgumentList
    A list of parameters to pass to Invoke-Command
    .PARAMETER ErrorMessage
    Optional error message. This will become part of the exception message we throw in case of an error.
    #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory=$true)]
        [Alias("Command")]
        [ScriptBlock]$ScriptBlock,
        [array]$ArgumentList=@(),
        [string]$ErrorMessage
    )
    PROCESS {
        if($LASTEXITCODE){
            # Leftover exit code. Some other process failed, and this
            # function was called before it was resolved.
            # There is no way to determine if the ScriptBlock contains
            # a powershell commandlet or a native application. So we clear out
            # the LASTEXITCODE variable before we execute. By this time, the value of
            # the variable is not to be trusted for error detection anyway.
            $LASTEXITCODE = ""
        }
        $res = Invoke-Command -ScriptBlock $ScriptBlock -ArgumentList $ArgumentList
        if ($LASTEXITCODE) {
            if(!$ErrorMessage){
                Throw ("Command exited with status: {0}" -f $LASTEXITCODE)
            }
            Throw ("{0} (Exit code: $LASTEXITCODE)" -f $ErrorMessage)
        }
        return $res
    }
}


function Wait-ProcessToFinish {
    Param(
        [Parameter(Mandatory=$true)]
        [String]$ProcessPath,
        [Parameter(Mandatory=$false)]
        [String[]]$ArgumentList,
        [Parameter(Mandatory=$false)]
        [String]$StandardOutput,
        [Parameter(Mandatory=$false)]
        [String]$StandardError,
        [Parameter(Mandatory=$false)]
        [int]$Timeout=7200
    )
    $parameters = @{
        'FilePath' = $ProcessPath
        'NoNewWindow' = $true
        'PassThru' = $true
    }
    if ($ArgumentList.Count -gt 0) {
        $parameters['ArgumentList'] = $ArgumentList
    }
    if ($StandardOutput) {
        $parameters['RedirectStandardOutput'] = $StandardOutput
    }
    if ($StandardError) {
        $parameters['RedirectStandardError'] = $StandardError
    }
    $process = Start-Process @parameters
    $errorMessage = "The process $ProcessPath didn't finish successfully"
    try {
        Wait-Process -InputObject $process -Timeout $Timeout -ErrorAction Stop
        Write-Output "Process finished within the timeout of $Timeout seconds"
    } catch [System.TimeoutException] {
        Write-Output "The process $ProcessPath exceeded the timeout of $Timeout seconds"
        Stop-Process -InputObject $process -Force -ErrorAction SilentlyContinue
        Throw $_
    }
    if($process.ExitCode -ne 0) {
        Write-Output "$errorMessage. Exit code: $($process.ExitCode)"
        Throw $errorMessage
    }
}

function Start-MesosCIProcess {
    Param(
        [Parameter(Mandatory=$true)]
        [string]$ProcessPath,
        [Parameter(Mandatory=$false)]
        [string[]]$ArgumentList,
        [Parameter(Mandatory=$true)]
        [string]$BuildErrorMessage
    )
    $command = $ProcessPath -replace '\\', '\\'
    if($ArgumentList.Count) {
        $ArgumentList | Foreach-Object { $command += " $($_ -replace '\\', '\\')" }
    }
    try {
        Wait-ProcessToFinish -ProcessPath $ProcessPath -ArgumentList $ArgumentList 
        $msg = "Successfully executed: $command"
    } catch {
        $msg = "Failed command: $command"
        $global:BUILD_STATUS = 'FAIL'
        Write-Output "Exception: $($_.ToString())"
        Throw $BuildErrorMessage
    } finally {
        Write-Output $msg
    }
}

function Start-MesosBuild {
    Write-Output "Creating mesos cmake makefiles"
    Push-Location $MESOS_BUILD_DIR
    try {
        $generatorName = "Visual Studio 15 2017 Win64"
        $parameters = @("$MESOS_GIT_REPO_DIR", "-G", "`"$generatorName`"", "-T", "host=x64", "-DENABLE_LIBEVENT=1")

        Start-MesosCIProcess -ProcessPath "cmake.exe" -ArgumentList $parameters -BuildErrorMessage "Mesos cmake files failed to generate."
            #-StdoutFileName "mesos-build-cmake-stdout.log" -StderrFileName "mesos-build-cmake-stderr.log"
    } finally {
        Pop-Location
    }
    Write-Output "mesos cmake makefiles were generated successfully"

    Write-Output "Started building Mesos binaries"
    Push-Location $MESOS_BUILD_DIR

    try {

        Start-MesosCIProcess -ProcessPath "cmake.exe" -ArgumentList @("--build", ".", "--", "/m") -BuildErrorMessage "Mesos binaries failed to build."
    } finally {
        Pop-Location
    }
    Write-Output "Mesos binaries were successfully built"


}


copy-item -Recurse "c:/pkg/src/" -destination "$MESOS_DIR"

New-Environment

Start-MesosBuild

#Copy build directory to destination directory. 
#For now we grab the whole lot
New-Item -itemtype directory "$env:PKG_PATH\bin"
Copy-Item -Path "$MESOS_BUILD_DIR\src\*" -Destination "$env:PKG_PATH\bin\" -Filter "*.exe"
