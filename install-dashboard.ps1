# Thin wrapper — install-dashboard.py does the actual work (JSON munging is messier
# in Windows PowerShell 5.1 than it's worth).
#
# Usage:
#   .\install-dashboard.ps1
#   .\install-dashboard.ps1 -Path u/admin/loan_dashboard
#   .\install-dashboard.ps1 -Workspace loan -Token xxx

[CmdletBinding()]
param(
    [string]$BaseUrl,
    [string]$Workspace,
    [string]$Token,
    [string]$Path,
    [string]$JsonFile
)

$argList = @("$PSScriptRoot\install-dashboard.py")
if ($BaseUrl)   { $argList += @('--base-url',  $BaseUrl) }
if ($Workspace) { $argList += @('--workspace', $Workspace) }
if ($Token)     { $argList += @('--token',     $Token) }
if ($Path)      { $argList += @('--path',      $Path) }
if ($JsonFile)  { $argList += @('--json-file', $JsonFile) }

& python @argList
exit $LASTEXITCODE
