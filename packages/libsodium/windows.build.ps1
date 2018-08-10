$ErrorActionPreference = "Stop"

$PKG_DIR = Join-Path $env:SystemDrive "pkg"
$LIB_SODIUM_DIR = Join-Path $env:SystemDrive "libsodium"


function Set-WindowsSDK {
    Param(
        [Parameter(Mandatory=$true)]
        [string]$VCXProjFile,
        [Parameter(Mandatory=$true)]
        [string]$Version
    )

    [xml]$settings = Get-Content $VCXProjFile
    $target = $settings.Project.PropertyGroup | Where-Object { $_.Label -eq "Globals" }
    if($target.WindowsTargetPlatformVersion) {
        $target.WindowsTargetPlatformVersion = $Version
    } else {
        $element = $settings.CreateElement('WindowsTargetPlatformVersion', $settings.DocumentElement.NamespaceURI)
        $element.InnerText = $Version
        $target.AppendChild($element) | Out-Null
    }
    $settings.Save($VCXProjFile)
}

function Start-LibsodiumBuild {
    # copy source to temporary build directory
    Copy-Item -Recurse -Path "$PKG_DIR/src/libsodium" -Destination $LIB_SODIUM_DIR
    Push-Location $LIB_SODIUM_DIR
    Write-Output "Starting the libsodium build"
    Set-WindowsSDK -VCXProjFile "$LIB_SODIUM_DIR\builds\msvc\vs2017\libsodium\libsodium.vcxproj" -Version "10.0.16299.0"
    MSBuild.exe "$LIB_SODIUM_DIR\builds\msvc\vs2017\libsodium.sln" /nologo /target:Build /p:Platform=x64 /p:Configuration=DynRelease
    if($LASTEXITCODE) {
        Throw "Failed to build lib sodium"
    }
}


Start-LibsodiumBuild
New-Item -ItemType "Directory" -Force -Path "$env:PKG_PATH\bin"
Copy-Item -Path "$LIB_SODIUM_DIR\bin\x64\Release\v141\dynamic\*" -Destination "$env:PKG_PATH\bin\"
New-Item -ItemType "Directory" -Force -Path "$env:PKG_PATH\include"
Copy-Item -Recurse -Path "$LIB_SODIUM_DIR\src\libsodium\include\*" -Destination "$env:PKG_PATH\include\"
