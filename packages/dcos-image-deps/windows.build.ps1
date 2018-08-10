$ErrorActionPreference = "Stop"

$MESOSPHERE_DIR = Join-Path $env:SystemDrive "opt\mesosphere"
$PYTHON_PREFIX = Join-Path $env:SystemDrive "Python"
$PKG_DIR = Join-Path $env:SystemDrive "pkg"


. "$MESOSPHERE_DIR\environment.export.ps1"

New-Item -ItemType "Directory" -Force -Path $PYTHON_PREFIX
$packages = @("adal", "analytics-python", "azure-nspkg", "azure-common", "azure-mgmt-nspkg",
              "azure-mgmt-network", "azure-storage", "beautifulsoup4", "docutils", "keyring",
              "msrest", "msrestazure", "py", "requests-oauthlib", "schema", "webob") 
foreach($package in $packages) {
    $whl = Get-Item "$PKG_DIR\src\$package\*.whl"
    $params = @("install", "--no-deps", "--no-index", "--prefix=$PYTHON_PREFIX", "$whl")
    $p = Start-Process -Wait -PassThru -FilePath "pip.exe" -ArgumentList $params
    if($p.ExitCode -ne 0) {
        Throw ("Failed to install $package Python library. Exit code: $($p.ExitCode)")
    }
}

$packages = @("aiohttp", "checksumdir", "coloredlogs", "docker-py", "humanfriendly", "multidict", 
              "oauthlib", "waitress", "websocket-client" )
foreach($package in $packages) {
    $params = @("install", "--no-deps", "--prefix=$PYTHON_PREFIX", "$PKG_DIR\src\$package")
    $p = Start-Process -Wait -PassThru -FilePath "pip.exe" -ArgumentList $params
    if($p.ExitCode -ne 0) {
        Throw ("Failed to install $package Python library. Exit code: $($p.ExitCode)")
    }
}

New-Item -ItemType "Directory" -Force -Path "$env:PKG_PATH\bin"
Copy-Item -Recurse -Path $PYTHON_PREFIX -Destination "$env:PKG_PATH\bin\"
