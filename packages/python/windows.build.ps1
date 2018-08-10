$ErrorActionPreference = "Stop"

$MESOSPHERE_DIR = Join-Path $env:SystemDrive "opt\mesosphere"
$PIP_TMP_DIR = Join-Path $env:SystemDrive "pip_tmp"
$PYTHON_PREFIX = Join-Path $env:SystemDrive "Python"
$PKG_DIR = Join-Path $env:SystemDrive "pkg"

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


. "$MESOSPHERE_DIR\environment.export.ps1"

New-Item -ItemType "Directory" -Force -Path $PIP_TMP_DIR

$params = @("-m", "ensurepip", "--root", $PIP_TMP_DIR)
Start-ExecuteWithRetry -ScriptBlock {
    $p = Start-Process -Wait -PassThru -FilePath "python.exe" -ArgumentList $params
    if($p.ExitCode -ne 0) {
        Throw ("Failed to install pip and setuptools. Exit code: $($p.ExitCode)")
    }
} -RetryMessage "Failed to install pip and setuptools. Retrying..."

Move-Item -Path "$PIP_TMP_DIR\opt\mesosphere\bin\Python" $PYTHON_PREFIX
Remove-Item -Recurse $PIP_TMP_DIR
Rename-Item -Path "$PYTHON_PREFIX\Scripts\pip3.exe" -NewName "$PYTHON_PREFIX\Scripts\pip.exe"
Rename-Item -Path "$PYTHON_PREFIX\Scripts\easy_install-3.6.exe" -NewName "$PYTHON_PREFIX\Scripts\easy_install.exe"

$env:PYTHONPATH = "$PYTHON_PREFIX\Lib;$PYTHON_PREFIX\Lib\site-packages"

$packages = @("pypiwin32", "pywin32")
foreach($package in $packages) {
    $whl = Get-Item "$PKG_DIR\src\$package\*.whl"
    $params = @("-m", "pip", "install", "--no-deps", "--no-index", "--prefix=$PYTHON_PREFIX", "$whl")
    $p = Start-Process -Wait -PassThru -FilePath "python.exe" -ArgumentList $params
    if($p.ExitCode -ne 0) {
        Throw ("Failed to install $package Python library. Exit code: $($p.ExitCode)")
    }
}

$packages = @("cython", "pywin32-ctypes")
foreach($package in $packages) {
    $params = @("-m", "pip", "install", "--no-deps", "--prefix=$PYTHON_PREFIX", "$PKG_DIR\src\$package")
    $p = Start-Process -Wait -PassThru -FilePath "python.exe" -ArgumentList $params
    if($p.ExitCode -ne 0) {
        Throw ("Failed to install $package Python library. Exit code: $($p.ExitCode)")
    }
}

New-Item -ItemType "Directory" -Force -Path "$env:PKG_PATH\bin"
Copy-Item -Recurse -Path $PYTHON_PREFIX -Destination "$env:PKG_PATH\bin\"
