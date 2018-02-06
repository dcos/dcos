#
#
#
#[void]$global:script_path # A declaration

#$TEMPLATES_DIR = Join-Path $PSScriptRoot "templates"
#

class Dcos-Metrics:Installable
{
    static [string] $ClassName = "Dcos-Metrics"
    [string] Setup( [string] $script_path,
           [string[]]$MasterAddress,
           [string]$AgentPrivateIP,
           [switch]$Public=$false
         ) { 

        Write-Host "Setup Dcos-Metrics : $script_path";

        try {

            #
            # Need to add
            #
        } catch {
            throw $_
        }
        Write-Output "Successfully finished setting up the Windows Dcos-Metrics Agent"
        return $true
    }
}



