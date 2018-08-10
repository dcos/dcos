$ErrorActionPreference = "Stop"

$MESOS_DIR = Join-Path $env:SystemDrive "mesos_tmp"
$MESOS_BUILD_DIR = Join-Path $MESOS_DIR "build"
$MESOS_GIT_DIR = Join-Path $MESOS_DIR "mesos"
$PKG_DIR = Join-Path $env:SystemDrive "pkg"


function Wait-ProcessToFinish {
    Param(
        [Parameter(Mandatory=$true)]
        [String]$ProcessPath,
        [Parameter(Mandatory=$false)]
        [String[]]$ArgumentList,
        [Parameter(Mandatory=$false)]
        [int]$Timeout=7200
    )
    $parameters = @{
        'FilePath' = $ProcessPath
        'NoNewWindow' = $true
        'PassThru' = $true
    }
    if ($ArgumentList.Count -gt 0) {
        $parameters['ArgumentList'] = $ArgumentList
    }
    $process = Start-Process @parameters
    $errorMessage = "The process $ProcessPath didn't finish successfully"
    try {
        Wait-Process -InputObject $process -Timeout $Timeout -ErrorAction Stop
        Write-Output "Process finished within the timeout of $Timeout seconds"
    } catch [System.TimeoutException] {
        Write-Output "The process $ProcessPath exceeded the timeout of $Timeout seconds"
        Stop-Process -InputObject $process -Force -ErrorAction SilentlyContinue
        Throw $_
    }
    if($process.ExitCode -ne 0) {
        Write-Output "$errorMessage. Exit code: $($process.ExitCode)"
        Throw $errorMessage
    }
}

function Start-MesosBuild {
    Copy-Item -Recurse "$PKG_DIR/src/mesos" -Destination "$MESOS_GIT_DIR"
    Push-Location $MESOS_BUILD_DIR
    $parameters = @("$MESOS_GIT_DIR", "-G", "`"Visual Studio 15 2017 Win64`"", "-T", "host=x64", "-DHAS_AUTHENTICATION=ON", "-DENABLE_LIBWINIO=ON")
    Wait-ProcessToFinish -ProcessPath "cmake.exe" -ArgumentList $parameters
    Write-Output "Start building Mesos binaries"
    $parameters = @("--build", ".", "--config", "Release", "--target", "mesos-agent", "-- /maxcpucount")
    Wait-ProcessToFinish -ProcessPath "cmake.exe" -ArgumentList $parameters
    Pop-Location
    Write-Output "Mesos binaries were successfully built"
}


New-Item -ItemType "Directory" -Force -Path $MESOS_DIR
New-Item -ItemType "Directory" -Force -Path $MESOS_BUILD_DIR
Start-MesosBuild

New-Item -ItemType "Directory" -Force -Path "$env:PKG_PATH\bin"
Copy-Item -Path "$MESOS_BUILD_DIR\src\*.exe" -Destination "$env:PKG_PATH\bin\"
Copy-Item -Path "$PKG_DIR\extra\mesos-agent-setup.ps1" -Destination "$env:PKG_PATH\bin\"

$agentServiceDir = Join-Path $env:PKG_PATH "dcos.target.wants_slave"
$agentPublicServiceDir = Join-Path $env:PKG_PATH "dcos.target.wants_slave_public"

New-Item -ItemType "Directory" -Force -Path $agentServiceDir
New-Item -ItemType "Directory" -Force -Path $agentPublicServiceDir

Copy-Item -Path "$PKG_DIR\extra\dcos-mesos-slave.windows.service" -Destination "$agentServiceDir\dcos-mesos-slave.service"
Copy-Item -Path "$PKG_DIR\extra\dcos-mesos-slave-public.windows.service" -Destination "$agentPublicServiceDir\dcos-mesos-slave-public.service"
