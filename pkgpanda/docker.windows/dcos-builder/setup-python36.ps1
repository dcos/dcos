$pip_url = 'https://bootstrap.pypa.io/get-pip.py'
$python_url = 'https://www.python.org/ftp/python/3.6.8/python-3.6.8-amd64.exe'
$pythonDownloadPath = Join-Path $env:TEMP "python-3.6.8-amd64.exe"
$pipDownloadPath = Join-Path $env:TEMP "get-pip.py"
$pythonInstallDir = Join-Path $env:SystemDrive "Python36"
$INSTALL_ARGS = @("/quiet InstallAllUsers=1 PrependPath=1 Include_test=0 TargetDir=$pythonInstallDir")

Invoke-WebRequest -UseBasicParsing -Uri $python_url -OutFile $pythonDownloadPath

If(!(test-path $pythonInstallDir))
{
      New-Item -ItemType Directory -Force -Path $pythonInstallDir
}

$parameters = @{
'FilePath' = $pythonDownloadPath
'ArgumentList' = $INSTALL_ARGS
'Wait' = $true
'PassThru' = $true
}

$p = Start-Process @parameters
if($p.ExitCode -ne 0) {
Throw "Failed to install $pythonDownloadPath"
}

[Environment]::SetEnvironmentVariable("PATH", "${env:path};${pythonInstallDir}\Scripts", "Machine") 
Invoke-WebRequest -UseBasicParsing -Uri $pip_url -OutFile $pipDownloadPath

& $pythonInstallDir\python.exe $pipDownloadPath --no-warn-script-location
