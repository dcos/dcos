#!/bin/pwsh
$headers = @{"Metadata" = "true"}
$r = Invoke-WebRequest -headers $headers "http://169.254.169.254/latest/meta-data/local-ipv4" -UseBasicParsing
$r.Content
