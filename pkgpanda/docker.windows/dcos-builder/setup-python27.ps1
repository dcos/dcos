$PROGRAM = "Python-2.7.13"
$DOWNLOAD_URL = "https://www.python.org/ftp/python/2.7.13/python-2.7.13.msi"
$INSTALL_DIR = Join-Path $env:SystemDrive "Python27"
$BIN_DIR =  Join-Path $INSTALL_DIR "bin"
$INSTALL_ARGS = @("/qn", "/i")

Write-Output "Downloading $PROGRAM from $DOWNLOAD_URL"
$fileName = $DOWNLOAD_URL.Split('/')[-1]
$downloadFilename = Join-Path $env:TEMP $fileName
Invoke-WebRequest -UseBasicParsing -Uri $DOWNLOAD_URL -OutFile $downloadFilename

$INSTALL_ARGS += $downloadFilename

$parameters = @{
    'FilePath' = "msiexec.exe"
    'ArgumentList' = $INSTALL_ARGS
    'Wait' = $true
    'PassThru' = $true
}
Write-Output "Installing $PROGRAM"
$p = Start-Process @parameters
if($p.ExitCode -ne 0) {
    Throw "Failed to install prerequisite $PROGRAM during the environment setup"
}

