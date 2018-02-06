$PROGRAM = "Erlang-19.3-64-bit"
$DOWNLOAD_URL = "http://erlang.org/download/otp_win64_19.3.exe"
$INSTALL_DIR = Join-Path $env:ProgramFiles "erlang"
$BIN_DIR =  Join-Path $INSTALL_DIR "bin"
$INSTALL_ARGS = @( "/S", "/D=$INSTALL_DIR" )
 
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

