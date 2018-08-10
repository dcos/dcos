$ErrorActionPreference = "Stop"

$FILENAME_PATH = "c:\temp\cmake-3.9.0-win64-x64.msi"

$parameters = @{
    'FilePath' = "msiexec.exe"
    'ArgumentList' = @("/quiet", "/i", $FILENAME_PATH)
    'Wait' = $true
    'PassThru' = $true
}
Write-Output "Installing $FILENAME_PATH"
$p = Start-Process @parameters
if($p.ExitCode -ne 0) {
    Throw "Failed to install $FILENAME_PATH"
}

# cmake has some OS race condition problems with file operations.
# bump settings a bit in a hope to solve this
$registryPath = "HKCU:\Software\Kitware\CMake\Config"
$retryCountName = "FilesystemRetryCount"
$retryCountValue = 10 # normal is 5
$retryDelayName = "FilesystemRetryDelay"
$retryDelayValue = 1000 # normal is 500
New-Item -Path $registryPath -Force | Out-Null
New-ItemProperty -Path $registryPath -Name $retryCountName -Value $retryCountValue -PropertyType DWORD -Force | Out-Null
New-ItemProperty -Path $registryPath -Name $retryDelayName -Value $retryDelayValue -PropertyType DWORD -Force | Out-Null
