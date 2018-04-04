$ErrorActionPreference = "stop"

Set-Location "c:/pkg/src"
Write-Host "Installing python to directory ${env:PKG_PATH}"

$tmpdir = "c:\python363.tmp"

$parameters = @{
    'FilePath' = "c:/pkg/src/python/python-3.6.3.exe"

    'ArgumentList' = @("/quiet", "/passive", "InstallAllUsers=1", "PrependPath=1", "Include_test=0", "Include_tcltk=0", "TargetDir=$tmpdir")
    'Wait' = $true
    'PassThru' = $true
}
$p = Start-Process @parameters
if ($p.ExitCode -ne 0) {
    Throw "Failed to install python-3.6.3"
}

& "$tmpdir\scripts\pip" install "--no-deps" "--install-option=`"--prefix=$tmpdir`"" "c:\pkg\src\cython\Cython-0.27.3"
if ($LASTEXITCODE -ne 0) {
    Throw "Failed to install Cython-0.27.3"
}

copy-item -recurse -path "$tmpdir\*" -destination "$env:PKG_PATH\"
