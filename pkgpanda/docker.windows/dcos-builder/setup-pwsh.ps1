# Install PowerShell 6+ so that Invoke-WebRequest has retry support
$ErrorActionPreference = "stop"

Invoke-Expression "& { $(Invoke-RestMethod -Uri 'https://aka.ms/install-powershell.ps1') } -UseMSI"
