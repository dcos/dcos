 param (
    [string]$pkg_inst_dpath
 )
New-Item -ItemType SymbolicLink -Path "$Env:windir\nssm.exe" -Target "$pkg_inst_dpath\bin\nssm.exe"
