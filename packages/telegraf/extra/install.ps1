Param (
[string]$pkg_inst_dpath
)

if (-not (Test-Path -LiteralPath "C:\Program Files\Telegraf")) {
	new-item -Path "C:\Program Files\Telegraf" -type directory
	copy-item -recurse  -Path $pkg_inst_dpath\etc\telegraf.conf -Destination "C:\Program Files\Telegraf\"
}

& $pkg_inst_dpath\bin\telegraf.exe --service install
Start-Service -Name telegraf
