$PROGRAM = "cmake-3.9.0-64-bit"
$DOWNLOAD_URL = "https://cmake.org/files/v3.9/cmake-3.9.0-win64-x64.msi"
$INSTALL_DIR = Join-Path $env:ProgramFiles "CMake"
$BIN_DIR =  Join-Path $INSTALL_DIR "bin"
$INSTALL_ARGS = @("/quiet", "/i")

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

