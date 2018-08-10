#!/bin/pwsh
$headers = @{"Metadata" = "true"}
$MAC = Get-WmiObject win32_networkadapterconfiguration | Select-Object macaddress
$r = Invoke-WebRequest -headers $headers ("http://169.254.169.254/latest/meta-data/network/interfaces/macs/" + $MAC[0] + "/ipv6s") -UseBasicParsing
$r.Content
