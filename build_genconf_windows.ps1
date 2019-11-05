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
$bsdtar = "C:\Program Files (x86)\GnuWin32\bin\bsdtar.exe"
$win_release_tar = "windows.release.tar"
$package_list = "latest.package_list.json"
Remove-Item -path "$artifact_storage\$package_list" -Force -ErrorAction SilentlyContinue
$latest = Get-ChildItem -Path "$artifact_storage\package_lists" | Sort-Object LastAccessTime -Descending | Select-Object -First 1
Copy-Item -Path "$artifact_storage\package_lists\$latest" "$artifact_storage\package_lists\$package_list" -Force -ErrorAction SilentlyContinue

# Pack content of package_lists, packages from artifact_storage dir into windows.release.tar:
echo "bsdtar: $bsdtar"
echo "artifact_storage: $artifact_storage"
dir $artifact_storage
echo "win_release_tar: $win_release_tar"
echo "Listing directory $PWD BEFORE Windows Tar Ball generation"
dir

& "$bsdtar" -C "$artifact_storage" -cvf "$win_release_tar" "package_lists" "packages"

# Set *win.sh template
$win_sh_template=@"
#!/bin/bash
# variant: $($variant)
#
# All logging and tool output should be redirected to stderr
# as the Docker container might output json that would
# otherwise be tainted.
#
set -o errexit -o nounset -o pipefail

# create genconf_win/serve dirs, if not extracted
if [ ! -d genconf_win/serve ]; then
    >&2 mkdir -p genconf_win/serve
fi


# extract payload into genconf_win/serve dirs, if not extracted
if [ ! -f "./genconf_win/serve)" ]; then
    >&2 echo Extracting windows relese tar artifact from this script
    sed '1,/^#EOF#$/d' "`$0" | tar xv --directory ./genconf_win/serve
fi
trap - INT

exit `$?

#EOF#

"@

# Seting content of win.sh template to the file:
echo $win_sh_template | Set-Content -NoNewline -Path "$($artifact_out)";
# Appending content of a win_release_tar file in a Byte format:
Get-Content -Encoding Byte -ReadCount 512 $($win_release_tar) | Add-Content -Path "$($artifact_out)" -Encoding Byte;
echo "Listing directory $PWD AFTER Windows Tar Ball generation"
dir