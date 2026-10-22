[CmdletBinding(SupportsShouldProcess = $true, ConfirmImpact = 'High')]
param(
    [Parameter(Mandatory = $true, Position = 0)][string]$Destination
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

# PowerShell 5.1 can propagate -WhatIf into Get-FileHash's provider lookup.
# These helpers perform read-only checks in a child scope; the removal scope
# retains the caller's WhatIf/Confirm preferences and its ShouldProcess gate.
function Get-ReadOnlyPackageHash([string]$Path) {
    $WhatIfPreference = $false
    return (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
}

function Assert-VerifiedPackage([string]$Root) {
    $WhatIfPreference = $false
    & (Join-Path $packageRoot 'verify.ps1') -PackageRoot $Root | Out-Null
}

function Assert-NoReparseComponents([string]$Path) {
    $full = [IO.Path]::GetFullPath($Path)
    $root = [IO.Path]::GetPathRoot($full)
    if (-not $root) { throw "Cannot resolve path root: $Path" }
    while ($full.Length -gt $root.Length -and ($full.EndsWith('\') -or $full.EndsWith('/'))) {
        $full = $full.Substring(0, $full.Length - 1)
    }
    $current = $root
    $tail = $full.Substring($root.Length)
    foreach ($component in ($tail -split '[\\/]')) {
        if (-not $component) { continue }
        $current = Join-Path $current $component
        $item = $null
        try {
            $item = Get-Item -LiteralPath $current -Force -ErrorAction Stop
        } catch {
            if (Test-Path -LiteralPath $current) { throw }
        }
        if ($null -ne $item) {
            if ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) {
                throw "Refusing a path containing a symlink, junction or other reparse point: $current"
            }
        }
    }
    return $full
}

function Get-ExpectedInventory($Manifest) {
    if ($Manifest.name -ne 'pixellayer' -or
        $Manifest.target -ne 'x86_64-pc-windows-msvc' -or
        [string]::IsNullOrWhiteSpace([string]$Manifest.version)) {
        throw 'The package manifest is not a PixelLayer Windows x64 build.'
    }
    $files = [Collections.Generic.HashSet[string]]::new([StringComparer]::Ordinal)
    $folded = [Collections.Generic.HashSet[string]]::new([StringComparer]::OrdinalIgnoreCase)
    $directories = [Collections.Generic.HashSet[string]]::new([StringComparer]::Ordinal)
    $hashes = [Collections.Generic.Dictionary[string, string]]::new([StringComparer]::Ordinal)
    foreach ($entry in $Manifest.files) {
        $relative = [string]$entry.path
        if ($relative -notmatch '^[A-Za-z0-9._/-]+$' -or $relative.StartsWith('/') -or
            $relative.EndsWith('/') -or $relative.Contains('//') -or
            ($relative -split '/') -contains '.' -or ($relative -split '/') -contains '..' -or
            [long]$entry.size_bytes -lt 0 -or [string]$entry.sha256 -notmatch '^[0-9a-f]{64}$') {
            throw "Unsafe or malformed manifest entry: $relative"
        }
        if (-not $folded.Add($relative)) { throw "Duplicate manifest path: $relative" }
        [void]$files.Add($relative)
        $hashes[$relative] = [string]$entry.sha256
        $parent = $relative
        while ($parent.Contains('/')) {
            $parent = $parent.Substring(0, $parent.LastIndexOf('/'))
            [void]$directories.Add($parent)
        }
    }
    foreach ($required in @('pixellayer.exe', 'uninstall.ps1', 'verify.ps1')) {
        if (-not $files.Contains($required)) { throw "Required package file absent from manifest: $required" }
    }
    if (-not $files.Add('manifest.json')) { throw 'manifest.json must not appear in its own file list.' }
    [void]$folded.Add('manifest.json')
    return @{ Files = $files; FoldedFiles = $folded; Directories = $directories; Hashes = $hashes }
}

function Assert-ExactInventory([string]$Root, $Inventory) {
    $pending = [Collections.Generic.Stack[string]]::new()
    $actualFiles = [Collections.Generic.HashSet[string]]::new([StringComparer]::Ordinal)
    $actualDirectories = [Collections.Generic.HashSet[string]]::new([StringComparer]::Ordinal)
    $pending.Push($Root)
    while ($pending.Count -gt 0) {
        $directory = $pending.Pop()
        foreach ($item in (Get-ChildItem -LiteralPath $directory -Force)) {
            if ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) {
                throw "Refusing package data containing a reparse point: $($item.FullName)"
            }
            $relative = $item.FullName.Substring($Root.Length + 1).Replace('\', '/')
            if ($item.PSIsContainer) {
                if (-not $Inventory.Directories.Contains($relative)) {
                    throw "Refusing to remove a directory not listed by the package: $relative"
                }
                [void]$actualDirectories.Add($relative)
                $pending.Push($item.FullName)
            } else {
                if (-not $Inventory.Files.Contains($relative)) {
                    throw "Refusing to remove a file not listed by the package: $relative"
                }
                [void]$actualFiles.Add($relative)
            }
        }
    }
    if ($actualFiles.Count -ne $Inventory.Files.Count -or
        $actualDirectories.Count -ne $Inventory.Directories.Count) {
        throw 'Package contents are missing or do not match the verified manifest; nothing was removed.'
    }
}

function Assert-NoPixelLayerProcess([string]$ExecutablePath) {
    try {
        $processes = @(Get-Process -Name 'pixellayer' -ErrorAction SilentlyContinue)
        foreach ($process in $processes) {
            $processPath = $process.Path
            if (-not $processPath) {
                throw "Cannot identify the path of active PixelLayer process $($process.Id); stop PixelLayer and retry."
            }
            if ([string]::Equals([IO.Path]::GetFullPath($processPath), $ExecutablePath,
                    [StringComparison]::OrdinalIgnoreCase)) {
                throw "PixelLayer is running from this installation (PID $($process.Id)). Disconnect the MCP client, stop the server, and retry."
            }
        }
    } catch {
        if ($_.Exception.Message -like 'Cannot identify the path*' -or
            $_.Exception.Message -like 'PixelLayer is running from this installation*') { throw }
        throw "Could not safely check for an active PixelLayer process: $($_.Exception.Message)"
    }
}

$packageRoot = Assert-NoReparseComponents $PSScriptRoot
$sourceManifestPath = Join-Path $packageRoot 'manifest.json'
if (-not (Test-Path -LiteralPath $sourceManifestPath -PathType Leaf)) {
    throw 'Run this script from a verified PixelLayer package directory.'
}
$sourceManifestItem = Get-Item -LiteralPath $sourceManifestPath -Force
if ($sourceManifestItem.Attributes -band [IO.FileAttributes]::ReparsePoint) {
    throw 'The source manifest must be a regular file.'
}
$sourceManifest = Get-Content -LiteralPath $sourceManifestPath -Raw -Encoding UTF8 | ConvertFrom-Json
$inventory = Get-ExpectedInventory $sourceManifest
Assert-VerifiedPackage $packageRoot
$inventory.Hashes['manifest.json'] = (Get-ReadOnlyPackageHash $sourceManifestPath)

$target = Assert-NoReparseComponents $Destination
$targetRoot = [IO.Path]::GetPathRoot($target)
if ([string]::Equals($target.TrimEnd([char[]]@('\', '/')), $targetRoot.TrimEnd([char[]]@('\', '/')),
        [StringComparison]::OrdinalIgnoreCase)) {
    throw 'Refusing to uninstall a filesystem root.'
}
$targetItem = $null
try { $targetItem = Get-Item -LiteralPath $target -Force -ErrorAction Stop } catch {
    if (Test-Path -LiteralPath $target) { throw }
}
if ($null -eq $targetItem) {
    Write-Output "PixelLayer installation is already absent: $target"
    return
}
if (-not $targetItem.PSIsContainer -or $targetItem.Attributes -band [IO.FileAttributes]::ReparsePoint) {
    throw 'The uninstall destination must be the regular installation directory.'
}
$targetManifestPath = Join-Path $target 'manifest.json'
if (-not (Test-Path -LiteralPath $targetManifestPath -PathType Leaf)) {
    throw 'The destination has no PixelLayer package manifest; nothing was removed.'
}
$targetManifestItem = Get-Item -LiteralPath $targetManifestPath -Force
if ($targetManifestItem.Attributes -band [IO.FileAttributes]::ReparsePoint) {
    throw 'The destination manifest is a reparse point; nothing was removed.'
}
$targetManifestHash = (Get-ReadOnlyPackageHash $targetManifestPath)
$sourceManifestHash = (Get-ReadOnlyPackageHash $sourceManifestPath)
if ($targetManifestHash -ne $sourceManifestHash) {
    throw 'The destination is a different build. Nothing was removed.'
}
Assert-ExactInventory $target $inventory
Assert-VerifiedPackage $target

$exePath = [IO.Path]::GetFullPath((Join-Path $target 'pixellayer.exe'))
Assert-NoPixelLayerProcess $exePath

# Probe every package file for an exclusive read handle before starting deletion.
# This catches ordinary Windows file locks before Remove-Item can partially run.
foreach ($relative in $inventory.Files) {
    $path = Join-Path $target ($relative -replace '/', '\')
    [void](Assert-NoReparseComponents $path)
    $stream = $null
    try {
        $stream = [IO.File]::Open($path, [IO.FileMode]::Open, [IO.FileAccess]::Read, [IO.FileShare]::None)
    } catch {
        throw "A package file is busy or unreadable ($relative). Stop PixelLayer and close software using this folder; nothing was removed."
    } finally {
        if ($stream) { $stream.Dispose() }
    }
}

if (-not $PSCmdlet.ShouldProcess($target, 'Remove this verified PixelLayer version only')) { return }

# Change away from the target first: PowerShell may have been launched with the
# installation directory as its current working directory.
$parent = Split-Path -Parent $target
Set-Location -LiteralPath $parent
foreach ($relative in $inventory.Files) {
    $path = Join-Path $target ($relative -replace '/', '\')
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
        throw "Package file changed during removal; the directory remains: $relative"
    }
    $item = Get-Item -LiteralPath $path -Force
    if ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) {
        throw "Package file became a reparse point; the directory remains: $relative"
    }
    $actual = (Get-ReadOnlyPackageHash $path)
    if ($actual -ne $inventory.Hashes[$relative]) {
        throw "Package file changed during removal; the directory remains: $relative"
    }
    [void](Assert-NoReparseComponents $path)
    Remove-Item -LiteralPath $path -Force -ErrorAction Stop
}
$orderedDirectories = @($inventory.Directories | Sort-Object { ($_ -split '/').Count } -Descending)
foreach ($relative in $orderedDirectories) {
    $path = Join-Path $target ($relative -replace '/', '\')
    [void](Assert-NoReparseComponents $path)
    $item = Get-Item -LiteralPath $path -Force
    if (-not $item.PSIsContainer -or $item.Attributes -band [IO.FileAttributes]::ReparsePoint) {
        throw "Package directory changed during removal; the directory remains: $relative"
    }
    if (@(Get-ChildItem -LiteralPath $path -Force).Count -ne 0) {
        throw "New or unlisted data appeared during removal; preserved at: $path"
    }
    [void](Assert-NoReparseComponents $path)
    Remove-Item -LiteralPath $path -Force -ErrorAction Stop
}
[void](Assert-NoReparseComponents $target)
if (@(Get-ChildItem -LiteralPath $target -Force).Count -ne 0) {
    throw "New or unlisted data appeared during removal; preserved at: $target"
}
Remove-Item -LiteralPath $target -Force -ErrorAction Stop
$remaining = $null
try { $remaining = Get-Item -LiteralPath $target -Force -ErrorAction Stop } catch {
    if (Test-Path -LiteralPath $target) { throw }
}
if ($null -ne $remaining -or (Test-Path -LiteralPath $target)) {
    throw "Removal did not complete; files remain at $target. No success is reported."
}
Write-Output "Removed verified PixelLayer installation: $target"
Write-Output 'Model cache, MCP configuration and separately installed skill were left unchanged.'
