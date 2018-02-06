#
#
#
#[void]$global:script_path # A declaration

 

class AdminRouter:Installable
{

   
    static [string] $ClassName = "AdminRouter"

    [string] Setup( 
           [string] $script_path,
           [string[]]$MasterAddress,
           [string]$AgentPrivateIP,
           [switch]$Public=$false
        ) {
        [Uri]    $URLRewrite_Plugin_Uri  = 'http://download.microsoft.com/download/D/D/E/DDE57C26-C62C-4C59-A1BB-31D58B36ADA2/rewrite_amd64_en-US.msi'
        [string] $URLRewrite_Plugin_File ="c:/dcos-download/rewrite_amd64_en-US.msi"

        [Uri]    $ARR_Plugin_Uri = "https://download.microsoft.com/download/E/9/8/E9849D6A-020E-47E4-9FD0-A023E99B54EB/requestRouter_amd64.msi"
        [string] $ARR_Plugin_File = "c:/dcos-download/requestRouter_amd64.msi"

        Write-Host "Setup AdminRouter : $script_path"; 
        
        Write-Host "install Web-Server"
        $rslt = (get-windowsfeature | where { $_.Name -like "Web-Server" })
        if (! $rslt -match "Installed") 
        {
            $rslt = (add-windowsfeature "Web-Server, Web-Mgmt-Tools" )
            if (!$rslt.Success) 
            {
                Write-Host "Could not install Web-Server"
            }
        }

        $rslt = (get-windowsfeature | where { $_.Name -like "Web-Request-Monitor" })
        if (! $rslt -match "Installed")
        {
            $rslt = (add-windowsfeature "Web-Request-Monitor" )
            if (!$rslt.Success)
            {
                Write-Host "Could not install Web-Request-Monitor"
            }
        }

        import-module WebAdministration

        Invoke-WebRequest -Uri $URLRewrite_Plugin_Uri -OutFile $URLRewrite_Plugin_File
        Start-Process $URLRewrite_Plugin_File  '/qn /l c:/tmp/rewrite.log' | Wait-Process

        if ($? -ne $true)
        {
            Write-Host "Could not install URL rewrite"
        } 

        Invoke-WebRequest -Uri $ARR_Plugin_Uri -OutFile $ARR_Plugin_File
        Start-Process $ARR_Plugin_File  '/qn /l c:/tmp/rewrite.log' | Wait-Process

        if ($? -ne $true)
        {
            Write-Host "Could not install Applcation Request Routing"
        } 

        # Now setup the adminrouter application

        $server_default_physicalpath = "c:\inetpub\wwwroot"

        $adminappgroup = new-item "IIS:\AppPools\AdminRouter"
        $adminrouter_dir = new-item -ItemType "Directory" "$env:SystemDrive:\inetpub\wwwroot\DCOS" -force
        New-Website -Name "adminrouter" -Port 61001 -IPAddress $agentPrivateIP -PhysicalPath $adminrouter_dir -ApplicationPool "AdminRouter"
        return $true
    }
}



