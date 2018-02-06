$PROGRAM = "Patch=2.5.9-7"
$DOWNLOAD_URL = "https://10gbps-io.dl.sourceforge.net/project/gnuwin32/patch/2.5.9-7/patch-2.5.9-7-setup.exe"
$INSTALL_DIR = Join-Path ${env:ProgramFiles(x86)} "GnuWin32"
$BIN_DIR =  Join-Path $INSTALL_DIR "bin"
$INSTALL_ARGS = @("/VERYSILENT","/SUPPRESSMSGBOXES","/SP-")

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

