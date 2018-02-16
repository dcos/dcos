$PROGRAM = "golang-1.9.3-64-bit"
$DOWNLOAD_URL = "https://golang.org/dl/go1.9.3.windows-amd64.zip"
$INSTALL_DIR = Join-Path $env:SystemDrive ""
$BIN_DIR =  Join-Path $INSTALL_DIR "bin"
 
Write-Output "Downloading $PROGRAM from $DOWNLOAD_URL"
$fileName = $DOWNLOAD_URL.Split('/')[-1]
$downloadFilename = Join-Path $env:TEMP $fileName
Invoke-WebRequest -UseBasicParsing -Uri $DOWNLOAD_URL -OutFile $downloadFilename

Write-Output "Extracting $PROGRAM"
Expand-Archive $downloadFilename -destinationpath $INSTALL_DIR

