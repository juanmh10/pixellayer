[CmdletBinding(SupportsShouldProcess = $true)]
param([string]$Destination)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Assert-VerifiedPackage([string]$PackageRoot) {
    # Hashing is read-only and must still run during -WhatIf previews.
    $WhatIfPreference = $false
    & (Join-Path $PSScriptRoot 'verify.ps1') -PackageRoot $PackageRoot
}

function Get-ReadOnlyPackageHash([string]$Path) {
    $WhatIfPreference = $false
    return (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash
}

$architecture = $env:PROCESSOR_ARCHITECTURE
if ($env:PROCESSOR_ARCHITEW6432) { $architecture = $env:PROCESSOR_ARCHITEW6432 }
if ($architecture -ne 'AMD64') { throw 'This package targets Windows x64 (AMD64).' }

Assert-VerifiedPackage $PSScriptRoot
$manifest = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'manifest.json') -Raw -Encoding UTF8 | ConvertFrom-Json
if (-not $Destination) {
    $Destination = Join-Path $env:LOCALAPPDATA "Programs\PixelLayer\$($manifest.version)"
}
$Destination = [IO.Path]::GetFullPath($Destination)
if (Test-Path -LiteralPath $Destination) {
    # Verify using the source verifier, then compare the exact trusted manifest.
    Assert-VerifiedPackage $Destination
    $sourceHash = (Get-ReadOnlyPackageHash (Join-Path $PSScriptRoot 'manifest.json'))
    $installedHash = (Get-ReadOnlyPackageHash (Join-Path $Destination 'manifest.json'))
    if ($sourceHash -ne $installedHash) { throw 'Destination contains a different build. Choose a new directory; existing installations are preserved.' }
    Write-Output "Already installed and verified: PixelLayer $($manifest.version) at $Destination"
    return
}
if (-not $PSCmdlet.ShouldProcess($Destination, 'Install PixelLayer files (no PATH or agent changes)')) { return }

$parent = Split-Path -Parent $Destination
[IO.Directory]::CreateDirectory($parent) | Out-Null
$staging = Join-Path $parent ('.pixellayer-install-' + [guid]::NewGuid().ToString('N'))
try {
    [IO.Directory]::CreateDirectory($staging) | Out-Null
    foreach ($entry in $manifest.files) {
        $target = Join-Path $staging $entry.path
        [IO.Directory]::CreateDirectory((Split-Path -Parent $target)) | Out-Null
        Copy-Item -LiteralPath (Join-Path $PSScriptRoot $entry.path) -Destination $target
    }
    Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'manifest.json') -Destination $staging
    Assert-VerifiedPackage $staging
    # Avoid running an EXE inside the directory immediately before renaming it.
    # Windows can briefly retain file handles after verification/launch. Retry
    # only the atomic move, with a bounded delay; never merge or replace a target.
    for ($attempt = 0; ; $attempt++) {
        try {
            [IO.Directory]::Move($staging, $Destination)
            break
        } catch [IO.IOException] {
            if ($attempt -ge 5 -or (Test-Path -LiteralPath $Destination)) { throw }
            Start-Sleep -Milliseconds (100 * [Math]::Pow(2, $attempt))
        } catch [UnauthorizedAccessException] {
            if ($attempt -ge 5 -or (Test-Path -LiteralPath $Destination)) { throw }
            Start-Sleep -Milliseconds (100 * [Math]::Pow(2, $attempt))
        }
    }
    # Recheck the final path too: a security product may remove a file after the
    # verified staging directory was moved. Report failure, not a valid install.
    Assert-VerifiedPackage $Destination
    # Installation verifies bytes without launching the program. Complete setup
    # executes the engine once for model preparation and the MCP draft.
    Write-Output "Installed verified PixelLayer $($manifest.version) at $Destination"
    Write-Output 'Models are not included. Configure the workspace and run model download explicitly when needed.'
} finally {
    if (Test-Path -LiteralPath $staging) { Remove-Item -LiteralPath $staging -Recurse -Force }
}
