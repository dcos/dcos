$ErrorActionPreference = "stop"

$PKG_DIR = "c:\pkg"

function Install-OpenSSL {
    Write-Output "installing openssl"
    # The argument options can be checked by running the installer
    # with `/help`.
    $p = Start-Process `
        -FilePath $PKG_DIR/src/openssl/Win64OpenSSL-1_1_1e.exe `
        -ArgumentList @("/VERYSILENT") `
        -NoNewWindow `
        -Wait `
        -PassThru
    if ($p.ExitCode -ne 0) {
        Throw "failed to install OpenSSL"
    }
}

function Patch-Mesos {
    Write-Output "patching mesos"
    Push-Location $PKG_DIR/src/mesos

    Get-ChildItem -Path $PKG_DIR/extra/windows-ee.patches -Filter "*.patch" | `
        ForEach-Object {
            git -c user.name="Mesosphere CI" -c `
                user.email="mesosphere-ci@users.noreply.github.com" `
                am $_.FullName
        }

    Pop-Location
}

function Build-Mesos {
    Write-Output "starting cmake config generation"
    Push-Location $PKG_DIR/src/mesos/build
    try {
        $p = Start-Process `
            -FilePath "cmake.exe" `
            -ArgumentList @(
                "..",
                "-G", '"Visual Studio 15 2017 Win64"',
                "-T", "host=x64",
                "-DENABLE_SSL=ON",
                "-DBUILD_TESTING=OFF"
            ) `
            -NoNewWindow `
            -Wait `
            -PassThru
        if ($p.ExitCode -ne 0) {
            Throw "cmake failed to generate config"
        }

        Write-Output "starting cmake build"
        $p = Start-Process `
            -FilePath "cmake.exe" `
            -ArgumentList @(
                "--build", ".",
                "--target", "mesos-agent",
                "--config", "Release",
                "--", "-m"
            ) `
            -NoNewWindow `
            -Wait `
            -PassThru
        if ($p.ExitCode -ne 0) {
            Throw "build failed"
        }
    } finally {
        Pop-Location
    }
}

New-Item -ItemType Directory -Force -Path $env:PKG_PATH/bin
New-Item -ItemType Directory -Force -Path $env:PKG_PATH/conf/modules
New-Item -ItemType Directory -Force -Path $PKG_DIR/src/mesos/build

Install-OpenSSL
Patch-Mesos
Build-Mesos

Copy-Item $PKG_DIR/src/mesos/build/src/*.exe $env:PKG_PATH/bin

Copy-Item $PKG_DIR/extra/mesos.nssm.j2 $env:PKG_PATH/conf
Copy-Item $PKG_DIR/extra/mesos.nssm-ssl.j2 $env:PKG_PATH/conf
Copy-Item $PKG_DIR/extra/mesos.extra.j2 $env:PKG_PATH/conf
Copy-Item $PKG_DIR/extra/mesos.ps1 $env:PKG_PATH/conf
