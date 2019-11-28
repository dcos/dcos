 param (
    [string]$pkg_inst_dpath
 )
Copy-Item "$pkg_inst_dpath\bin\nssm.exe" -Destination "c:\Windows" -force
