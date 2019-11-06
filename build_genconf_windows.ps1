param (
   [Parameter(Mandatory=$true)][string]$artifact_storage,
   [Parameter(Mandatory=$false)][string]$variant = ""
)

if ( $variant -eq "ee" ) {
    $artifact_out = "dcos_generate_config_win.$($variant).sh"
}
else {
    $artifact_out = "dcos_generate_config_win.sh"
}

# Generate windows.release.tar with help of bsdtar.exe:
$bsdtar = "C:\Program Files (x86)\GnuWin32\bin\bsdtar.exe";
$win_release_tar = "windows.release.tar";
$package_list = "latest.package_list.json";
Remove-Item -path "$artifact_storage\$package_list" -Force -ErrorAction SilentlyContinue;
$latest = Get-ChildItem -Path "$artifact_storage\package_lists" | Sort-Object LastAccessTime -Descending | Select-Object -First 1;
Copy-Item -Path "$artifact_storage\package_lists\$latest" "$artifact_storage\package_lists\$package_list" -Force -ErrorAction SilentlyContinue;

# Copying dcos_install.ps1 to cache location for further packing:
mkdir -f "$($artifact_storage)\prerequisites";
Copy-Item -Path ".\gen\build_deploy\powershell\dcos_install.ps1" "$artifact_storage\prerequisites\dcos_install.ps1" -Force -ErrorAction SilentlyContinue;

# Pack content of package_lists, packages from artifact_storage dir into windows.release.tar:
echo "bsdtar: $bsdtar";
echo "artifact_storage: $artifact_storage";
dir $artifact_storage;
echo "win_release_tar: $win_release_tar";
echo "Listing directory $PWD BEFORE Windows Tar Ball generation";
dir;

# List files to be added to $win_release_tar:
& "$bsdtar" -C "$artifact_storage" -cvf "$win_release_tar" "package_lists" "packages" "prerequisites"

# Seting content of .\gen\build_deploy\powershell\dcos_generate_config_win.sh.in template to the file:
(Get-Content -Path .\gen\build_deploy\powershell\dcos_generate_config_win.sh.in -Raw) -Replace "`r`n", "`n" | Set-Content -NoNewline -Path "$($artifact_out)";
# Appending content of a win_release_tar file in a Byte format:
Get-Content -Encoding Byte -ReadCount 512 $($win_release_tar) | Add-Content -Path "$($artifact_out)" -Encoding Byte;
echo "Listing directory $PWD AFTER Windows Tar Ball generation"
dir;
