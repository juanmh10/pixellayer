[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$Workspace,
    [string]$Destination,
    [string]$CacheDirectory,
    [string]$Client,
    [string]$Existing,
    [switch]$WslInterop,
    [switch]$AcceptDownload
)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$manifest = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'manifest.json') -Raw -Encoding UTF8 | ConvertFrom-Json
if (-not $Destination) { $Destination = Join-Path $env:LOCALAPPDATA "Programs\PixelLayer\$($manifest.version)" }
if (-not $CacheDirectory) {
    if ($env:PIXELLAYER_MODELS_CACHE) { $CacheDirectory = $env:PIXELLAYER_MODELS_CACHE }
    else { $CacheDirectory = Join-Path $env:LOCALAPPDATA 'PixelLayer\models' }
}
$Workspace = (Resolve-Path -LiteralPath $Workspace).Path
$Destination = [IO.Path]::GetFullPath($Destination)
$CacheDirectory = [IO.Path]::GetFullPath($CacheDirectory)
# Keep program-only install available for portable/technical workflows. Standard
# setup adds the verified FP32 model and returns one selected MCP draft.
$installLog = & (Join-Path $PSScriptRoot 'install.ps1') -Destination $Destination
foreach ($line in $installLog) { [Console]::Error.WriteLine($line) }
$exe = Join-Path $Destination 'pixellayer.exe'
$arguments = @('--workspace', $Workspace, '--cache-dir', $CacheDirectory, 'setup')
if ($AcceptDownload) { $arguments += '--accept-download' }
if ($Client) { $arguments += @('--client', $Client) }
if ($Existing) { $arguments += @('--existing', (Resolve-Path -LiteralPath $Existing).Path) }
if ($WslInterop) { $arguments += '--wsl-interop' }
& $exe @arguments
if ($LASTEXITCODE -ne 0) { throw 'Complete setup failed. Use the reported error; do not change antivirus settings or repeat program installation.' }
