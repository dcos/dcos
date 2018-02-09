$PROGRAM = "Git 2.16.1-64-bit"
$DOWNLOAD_URL = "https://github.com/git-for-windows/git/releases/download/v2.16.1.windows.1/Git-2.16.1-64-bit.exe"
$INSTALL_DIR = Join-Path $env:ProgramFiles "Git"
$BIN_DIR =  Join-Path $INSTALL_DIR "bin"
$INSTALL_ARGS = @("/SILENT")

Write-Output "Downloading $PROGRAM from $DOWNLOAD_URL"
$fileName = $DOWNLOAD_URL.Split('/')[-1]
$downloadFilename = Join-Path $env:TEMP $fileName
Invoke-WebRequest -UseBasicParsing -Uri $DOWNLOAD_URL -OutFile $downloadFilename

$parameters = @{
    'FilePath' = $downloadFilename
    'ArgumentList' = $INSTALL_ARGS
    'Wait' = $true
    'PassThru' = $true
}
Write-Output "Installing $PROGRAM"
$p = Start-Process @parameters
if($p.ExitCode -ne 0) {
    Throw "Failed to install prerequisite $PROGRAM during the environment setup"
}

