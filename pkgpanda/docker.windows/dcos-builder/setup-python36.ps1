$pythonDownloadPath = 'c:\temp\python-3.6.8-amd64.exe'
$pythonInstallDir = Join-Path $env:SystemDrive "Python36"
$pip_url = 'https://bootstrap.pypa.io/get-pip.py'
$INSTALL_ARGS = @("/quiet InstallAllUsers=1 PrependPath=1 Include_test=0 TargetDir=$pythonInstallDir")

$parameters = @{
'FilePath' = $pythonDownloadPath
'ArgumentList' = $INSTALL_ARGS
'Wait' = $true
'PassThru' = $true
}

$p = Start-Process @parameters
if($p.ExitCode -ne 0) {
Throw "Failed to install $FILENAME_PATH"
}

[Environment]::SetEnvironmentVariable("PATH", "${env:path};${pythonInstallDir}\Scripts", "Machine") 
Invoke-WebRequest -UseBasicParsing -Uri $pip_url -OutFile 'c:\temp\get-pip.py'

& $pythonInstallDir\python.exe 'c:\temp\get-pip.py' --no-warn-script-location



