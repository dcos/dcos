#
#
#
#$TEMPLATES_DIR = Join-Path $PSScriptRoot "templates"
#


$ERLANG_URL          = "$LOG_SERVER_BASE_URL/downloads/erl8.3.zip"
$VCREDIST_2013_URL = "https://download.microsoft.com/download/2/E/6/2E61CFA4-993B-4DD4-91DA-3737CD5CD6E3/vcredist_x64.exe"
$global:ERLANG_DIR = Join-Path $DCOS_DIR "erl8.3"
$global:ErtsDir      = Join-Path $ERLANG_DIR "erts-8.3"

function Install-VCredist {
    Write-Output "Install VCredist 2013"
    $installerPath = Join-Path $global:dcos_download "vcredist_2013_x64.exe"
    Invoke-WebRequest -UseBasicParsing -Uri $VCREDIST_2013_URL -OutFile $installerPath
    $p = Start-Process -Wait -PassThru -FilePath $installerPath -ArgumentList @("/install", "/passive")
    if ($p.ExitCode -ne 0) {
        Throw ("Failed install VCredist 2013. Exit code: {0}" -f $p.ExitCode)
    }
    Write-Output "Finished to install VCredist 2013 x64"
    Remove-Item $installerPath
}

function Install-Erlang {
    param ( 
        [string] $ScriptPath,
        [string] $ErlangDir,
        [string] $TemplatesDir
    )
    New-Directory -RemoveExisting $ErlangDir
    $erlangZip = Join-Path $global:dcos_download "erlang.zip"
    Write-Output "Downloading the Windows Erlang runtime zip"
    Invoke-WebRequest -UseBasicParsing -Uri $ERLANG_URL -OutFile $erlangZip
    Write-Output "Extracting the Windows Erlang zip to $ErlangDir"
    Expand-Archive -LiteralPath $erlangZip -DestinationPath $ErlangDir
    Remove-Item $erlangZip
    $binDir = "$global:ErtsDir\bin" -replace '\\', '\\'
    $rootDir = $ErlangDir -replace '\\', '\\'
    $context = @{
        'bin_dir' = $binDir
        'root_dir' = $rootDir
    }
    import-module "$ScriptPath/../templating/extra/Templating.psm1"
    . "$script_path/../templating/extra/Load-Assemblies.ps1"

    # Build the erl.ini once, place it twice
    $content = Invoke-RenderTemplateFromFile -Context $context -Template "$TemplatesDir\erl.ini"
    try {
        [System.IO.File]::WriteAllText("$ErlangDir\bin\erl.ini", $content)
    } 
    catch {
        Write-Output "could not write file"
        throw $_
    }

    try {
        [System.IO.File]::WriteAllText("$global:ErtsDir\bin\erl.ini", $content)
    }
    catch {
        Write-Output "could not write file"
        throw $_
    }
}

class Erts:Installable
{
    static [string] $ClassName = "Erts"
    [string] Setup( [string] $script_path,
           [string[]]$MasterAddress,
           [string]$AgentPrivateIP,
           [switch]$Public=$false
         ) { 
        Write-Host "Setup Erts : $script_path";

        try {
            Install-VCredist
            Install-Erlang -ScriptPath $script_path -ErlangDir $global:ERLANG_DIR -TemplatesDir $script_path/extra
        } catch {
            throw $_
        }
        Write-Output "Successfully finished setting up the Windows Erlang Runtime"
        return $true
    }
}



