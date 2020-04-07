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

function Build-Mesos {
    Write-Output "[mesos] starting cmake config generation"
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
            Throw "[mesos] cmake failed to generate config"
        }

        Write-Output "[mesos] starting cmake build"
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
            Throw "[mesos] build failed"
        }
    } finally {
        Pop-Location
    }
}

function Build-Mesos-Modules {
    Write-Output "[mesos-modules] starting cmake config generation"
    Push-Location $PKG_DIR/src/mesos-modules/build
    try {
        $p = Start-Process `
            -FilePath "cmake.exe" `
            -ArgumentList @(
                "..",
                "-G", '"Visual Studio 15 2017 Win64"',
                "-T", "host=x64",
                "-DBUILD_TESTING=OFF"
            ) `
            -NoNewWindow `
            -Wait `
            -PassThru
        if ($p.ExitCode -ne 0) {
            Throw "[mesos-modules] cmake failed to generate config"
        }

        Write-Output "[mesos-modules] starting cmake build"
        $p = Start-Process `
            -FilePath "cmake.exe" `
            -ArgumentList @(
                "--build", ".",
                "--config", "Release",
                "--", "-m"
            ) `
            -NoNewWindow `
            -Wait `
            -PassThru
        if ($p.ExitCode -ne 0) {
            Throw "[mesos-modules] build failed"
        }
    } finally {
        Pop-Location
    }
}

New-Item -ItemType Directory -Force -Path $env:PKG_PATH/bin
New-Item -ItemType Directory -Force -Path $PKG_DIR/src/mesos/build
New-Item -ItemType Directory -Force -Path $PKG_DIR/src/mesos-modules/build

Install-OpenSSL
# TODO(akornatskyy): get rid of extra mesos build
# see https://jira.d2iq.com/browse/D2IQ-65779
Build-Mesos
Build-Mesos-Modules

Copy-Item $PKG_DIR/src/mesos-modules/build/journald/Release/libjournaldlogger.dll `
    $env:PKG_PATH/bin
Copy-Item $PKG_DIR/src/mesos-modules/build/Release/metrics.dll `
    $env:PKG_PATH/bin
