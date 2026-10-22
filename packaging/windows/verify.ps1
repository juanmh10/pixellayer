[CmdletBinding()]
param([string]$PackageRoot = $PSScriptRoot)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$root = (Resolve-Path -LiteralPath $PackageRoot).Path
$manifest = Get-Content -LiteralPath (Join-Path $root 'manifest.json') -Raw -Encoding UTF8 | ConvertFrom-Json
if ($manifest.name -ne 'pixellayer' -or $manifest.target -ne 'x86_64-pc-windows-msvc') {
    throw 'This is not a PixelLayer Windows x64 manifest.'
}
if (@($manifest.files).Count -lt 1) { throw 'Empty package manifest.' }
$seen = @{}
foreach ($entry in $manifest.files) {
    $relative = [string]$entry.path
    if ([string]::IsNullOrWhiteSpace($relative) -or [IO.Path]::IsPathRooted($relative) -or
        $relative.Contains(':') -or ($relative -split '[/\\]') -contains '..') {
        throw "Invalid manifest path: $relative"
    }
    if ($seen.ContainsKey($relative)) { throw "Duplicate manifest path: $relative" }
    $seen[$relative] = $true
    $path = Join-Path $root $relative
    $file = Get-Item -LiteralPath $path
    if ($file.PSIsContainer -or ($file.Attributes -band [IO.FileAttributes]::ReparsePoint)) {
        throw "Expected a regular package file: $relative"
    }
    if ($file.Length -ne $entry.size_bytes) { throw "Size mismatch: $relative" }
    $actual = (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash
    if ($actual -ne $entry.sha256) { throw "SHA-256 mismatch: $relative" }
}
foreach ($required in @('pixellayer.exe', 'onnxruntime.dll', 'onnxruntime_providers_shared.dll',
                       'msvcp140.dll', 'msvcp140_1.dll', 'vcruntime140.dll', 'vcruntime140_1.dll',
                       'install.ps1', 'uninstall.ps1', 'verify.ps1', 'README.md')) {
    if (-not $seen.ContainsKey($required)) { throw "Required file absent from manifest: $required" }
}
Write-Output "Verified PixelLayer $($manifest.version): $($manifest.files.Count) files."
