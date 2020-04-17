$ErrorActionPreference = "stop"

$PKG_DIR = "c:\pkg"

function Install-OpenSSL {
    Write-Output "installing openssl"
    # The argument options can be checked by running the installer
    # with `/help`.
    $p = Start-Process `
        -FilePath $PKG_DIR/src/openssl/Win64OpenSSL-1_1_1f.exe `
        -ArgumentList @("/VERYSILENT") `
        -NoNewWindow `
        -Wait `
        -PassThru
    if ($p.ExitCode -ne 0) {
        Throw "failed to install OpenSSL"
    }
}

New-Item -ItemType Directory -Force -Path $env:PKG_PATH/bin
New-Item -ItemType Directory -Force -Path $env:PKG_PATH/include
New-Item -ItemType Directory -Force -Path $env:PKG_PATH/lib

Install-OpenSSL

Copy-Item "C:/Program Files/OpenSSL-Win64/bin/*" $env:PKG_PATH/bin -Recurse
Copy-Item "C:/Program Files/OpenSSL-Win64/include/*" $env:PKG_PATH/include -Recurse
Copy-Item "C:/Program Files/OpenSSL-Win64/lib/*" $env:PKG_PATH/lib -Recurse
