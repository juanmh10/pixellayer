[CmdletBinding()]
param(
    [string]$RuntimeDirectory,
    [string]$VCRedistDirectory,
    [string]$OutputDirectory
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$target = 'x86_64-pc-windows-msvc'
$runtimeVersion = '1.22.0'
$runtimePin = @(Get-Content -LiteralPath (Join-Path $root 'packaging\onnxruntime.tsv') | Where-Object { $_ -match '^win-x64\s+' })
if ($runtimePin.Count -ne 1) { throw 'Missing Windows runtime checksum.' }
$runtimeArchiveHash = ($runtimePin[0] -split '\s+')[1]
$utf8 = New-Object System.Text.UTF8Encoding($false)

function Write-Utf8([string]$Path, [string]$Text) {
    [IO.File]::WriteAllText($Path, $Text, $utf8)
}

Push-Location $root
try {
    & cargo build --release --locked --target $target
    if ($LASTEXITCODE -ne 0) { throw 'Rust release build failed.' }
    $metadataText = & cargo metadata --locked --offline --filter-platform $target --format-version 1
    if ($LASTEXITCODE -ne 0) { throw 'Cargo metadata failed.' }
    $metadata = ($metadataText -join "`n") | ConvertFrom-Json
    $project = @($metadata.packages | Where-Object { $_.name -eq 'pixellayer' -and -not $_.source })[0]
    $version = $project.version
    $name = "pixellayer-$version-windows-x64"
    if (-not $OutputDirectory) { $OutputDirectory = Join-Path $root 'dist' }
    $OutputDirectory = [IO.Path]::GetFullPath($OutputDirectory)
    [IO.Directory]::CreateDirectory($OutputDirectory) | Out-Null
    $package = Join-Path $OutputDirectory $name
    $zip = "$package.zip"
    if ((Test-Path -LiteralPath $package) -or (Test-Path -LiteralPath $zip)) {
        throw 'Package output already exists. Choose a fresh -OutputDirectory.'
    }

    if (-not $RuntimeDirectory) {
        $RuntimeDirectory = Join-Path $root ".local\runtime\onnxruntime-win-x64-$runtimeVersion"
        if (-not (Test-Path -LiteralPath $RuntimeDirectory)) {
            $archive = Join-Path $root ".local\runtime\onnxruntime-win-x64-$runtimeVersion.zip"
            [IO.Directory]::CreateDirectory((Split-Path -Parent $archive)) | Out-Null
            if (-not (Test-Path -LiteralPath $archive)) {
                $download = "$archive.download"
                try {
                    $ProgressPreference = 'SilentlyContinue'
                    Invoke-WebRequest -UseBasicParsing -Uri "https://github.com/microsoft/onnxruntime/releases/download/v$runtimeVersion/onnxruntime-win-x64-$runtimeVersion.zip" -OutFile $download
                    if ((Get-FileHash -LiteralPath $download -Algorithm SHA256).Hash -ne $runtimeArchiveHash) {
                        throw 'Runtime archive checksum mismatch.'
                    }
                    Move-Item -LiteralPath $download -Destination $archive
                } finally {
                    if (Test-Path -LiteralPath $download) { Remove-Item -LiteralPath $download }
                }
            }
            if ((Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash -ne $runtimeArchiveHash) {
                throw 'Runtime archive checksum mismatch.'
            }
            Expand-Archive -LiteralPath $archive -DestinationPath (Split-Path -Parent $RuntimeDirectory)
        }
    }
    $RuntimeDirectory = (Resolve-Path -LiteralPath $RuntimeDirectory).Path
    if ((Get-Content -LiteralPath (Join-Path $RuntimeDirectory 'VERSION_NUMBER') -Raw).Trim() -ne $runtimeVersion) {
        throw 'Expected ONNX Runtime CPU 1.22.0.'
    }
    $runtimeHashes = @{
        'onnxruntime.dll' = '579b636403983254346a5c1d80bd28f1519cd1e284cd204f8d4ff41f8d711559'
        'onnxruntime_providers_shared.dll' = 'ba00ea1ef846c9b909c7854bc56c51051a20f9773b3e1153dda118d4b85d0b93'
    }
    foreach ($dll in $runtimeHashes.Keys) {
        if ((Get-FileHash -LiteralPath (Join-Path $RuntimeDirectory "lib\$dll") -Algorithm SHA256).Hash -ne $runtimeHashes[$dll]) {
            throw "Runtime DLL differs from the pinned Windows x64 artifact: $dll"
        }
    }

    if (-not $VCRedistDirectory) {
        $vswhere = Join-Path ${env:ProgramFiles(x86)} 'Microsoft Visual Studio\Installer\vswhere.exe'
        $vs = & $vswhere -latest -products '*' -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath
        if ($LASTEXITCODE -ne 0 -or -not $vs) { throw 'Pass -VCRedistDirectory pointing to the official x64 Microsoft.VC*.CRT redist folder.' }
        $redistRoot = Join-Path ($vs | Select-Object -First 1) 'VC\Redist\MSVC'
        $redistVersions = Get-ChildItem -LiteralPath $redistRoot -Directory |
            Where-Object { $_.Name -match '^\d+\.\d+\.\d+$' } |
            Sort-Object { [version]$_.Name } -Descending
        foreach ($candidate in $redistVersions) {
            $crt = @(Get-ChildItem -Path (Join-Path $candidate.FullName 'x64\Microsoft.VC*.CRT') -Directory -ErrorAction SilentlyContinue)
            if ($crt.Count) { $VCRedistDirectory = $crt[0].FullName; break }
        }
    }
    if (-not $VCRedistDirectory) { throw 'The x64 Visual C++ redistributable DLLs were not found.' }
    $VCRedistDirectory = (Resolve-Path -LiteralPath $VCRedistDirectory).Path
    if ($VCRedistDirectory -match 'debug_nonredist|onecore') { throw 'Use the desktop release x64 redistributable folder.' }
    foreach ($dll in @('msvcp140.dll', 'msvcp140_1.dll', 'vcruntime140.dll', 'vcruntime140_1.dll')) {
        if (-not (Test-Path -LiteralPath (Join-Path $VCRedistDirectory $dll))) { throw "Missing CRT file: $dll" }
    }

    [IO.Directory]::CreateDirectory($package) | Out-Null
    $licenses = Join-Path $package 'licenses'
    [IO.Directory]::CreateDirectory($licenses) | Out-Null
    Copy-Item -LiteralPath (Join-Path $metadata.target_directory "$target\release\pixellayer.exe") -Destination $package
    foreach ($dll in @('onnxruntime.dll', 'onnxruntime_providers_shared.dll')) {
        Copy-Item -LiteralPath (Join-Path $RuntimeDirectory "lib\$dll") -Destination $package
    }
    Copy-Item -Path (Join-Path $VCRedistDirectory '*.dll') -Destination $package
    Copy-Item -Path (Join-Path $root 'packaging\windows\*') -Destination $package
    Copy-Item -LiteralPath (Join-Path $RuntimeDirectory 'LICENSE') -Destination (Join-Path $licenses 'ONNX-Runtime-MIT.txt')
    Copy-Item -LiteralPath (Join-Path $RuntimeDirectory 'ThirdPartyNotices.txt') -Destination (Join-Path $licenses 'ONNX-Runtime-ThirdPartyNotices.txt')
    Copy-Item -LiteralPath (Join-Path $root 'licenses\BiRefNet-MIT.txt') -Destination (Join-Path $licenses 'BiRefNet-MIT.txt')
    Copy-Item -LiteralPath (Join-Path $root 'licenses\ONNX-Runtime-MIT.txt') -Destination (Join-Path $licenses 'ONNX-Runtime-MIT.txt')
    Copy-Item -LiteralPath (Join-Path $root 'LICENSE') -Destination (Join-Path $licenses 'PixelLayer-MIT.txt')
    Copy-Item -LiteralPath (Join-Path $root 'Cargo.toml') -Destination (Join-Path $licenses 'PixelLayer-Cargo.toml')
    Write-Utf8 (Join-Path $licenses 'PixelLayer.txt') "PixelLayer declares MIT licensing in Cargo.toml. See PixelLayer-MIT.txt when included.`n"
    Write-Utf8 (Join-Path $licenses 'Microsoft-VC-Runtime.txt') @'
Microsoft Visual C++ runtime components

These unmodified x64 DLLs are copied from the installed Visual Studio Build Tools
VC/Redist/MSVC release CRT directory. They remain Microsoft components governed
by their applicable Microsoft terms; the PixelLayer MIT declaration does not
relicense them. Do not use debug_nonredist or arbitrary System32 DLL copies.

https://learn.microsoft.com/en-us/visualstudio/releases/2022/redistribution
https://learn.microsoft.com/en-us/cpp/windows/redistributing-visual-cpp-files
https://learn.microsoft.com/en-us/cpp/windows/choosing-a-deployment-method

Application-local deployment is used so no machine-wide runtime installer is run.
Bundled runtime updates require rebuilding/replacing this application package.
'@

    # Include registry dependency metadata and bundled license/notice files; no host paths.
    $notice = New-Object Text.StringBuilder
    [void]$notice.AppendLine('Rust dependencies: source metadata and upstream license notices')
    $resolved = @{}
    foreach ($node in $metadata.resolve.nodes) { $resolved[$node.id] = $true }
    foreach ($dependency in ($metadata.packages | Sort-Object name, version)) {
        if ($dependency.name -eq 'pixellayer' -or -not $resolved.ContainsKey($dependency.id)) { continue }
        [void]$notice.AppendLine("`n===== $($dependency.name) $($dependency.version) =====")
        [void]$notice.AppendLine("License metadata: $($dependency.license)")
        [void]$notice.AppendLine("Repository: $($dependency.repository)")
        $crateRoot = Split-Path -Parent $dependency.manifest_path
        $texts = @(Get-ChildItem -LiteralPath $crateRoot -Recurse -File | Where-Object {
            $_.Name -match '^(LICENSE|LICENCE|COPYING|COPYRIGHT|NOTICE)([-._].*)?$'
        })
        if ($dependency.license_file) {
            $licensePath = Join-Path $crateRoot $dependency.license_file
            if (Test-Path -LiteralPath $licensePath) { $texts += Get-Item -LiteralPath $licensePath }
        }
        foreach ($text in ($texts | Sort-Object FullName -Unique)) {
            [void]$notice.AppendLine("--- $($text.FullName.Substring($crateRoot.Length + 1).Replace('\','/')) ---")
            [void]$notice.AppendLine([IO.File]::ReadAllText($text.FullName))
        }
    }
    Write-Utf8 (Join-Path $licenses 'Rust-ThirdPartyNotices.txt') $notice.ToString()

    $engineCommit = (& git log -1 --format=%H -- rust Cargo.toml Cargo.lock rust-toolchain.toml).Trim()
    $files = @(Get-ChildItem -LiteralPath $package -Recurse -File | Sort-Object FullName | ForEach-Object {
        [pscustomobject][ordered]@{ path = $_.FullName.Substring($package.Length + 1).Replace('\','/');
            size_bytes = $_.Length; sha256 = (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash.ToLowerInvariant() }
    })
    $sourceCommit = (& git rev-parse HEAD).Trim()
    $sourceDirty = [bool](& git status --porcelain --untracked-files=no)
    if ($sourceDirty) { throw 'Public release packaging requires a clean tracked source tree.' }
    $manifest = [ordered]@{ name = 'pixellayer'; version = $version; target = $target;
        distribution = 'public-windows-v1';
        source_commit = $sourceCommit;
        source_dirty = $sourceDirty;
        rustc = (& rustc --version).Trim();
        engine_commit = $engineCommit; onnx_runtime_version = $runtimeVersion;
        vc_runtime_version = [Diagnostics.FileVersionInfo]::GetVersionInfo((Join-Path $package 'vcruntime140.dll')).FileVersion;
        model_included = $false; files = $files }
    Write-Utf8 (Join-Path $package 'manifest.json') ($manifest | ConvertTo-Json -Depth 6)
    & (Join-Path $package 'verify.ps1') -PackageRoot $package
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    Add-Type -AssemblyName System.IO.Compression
    $archive = [IO.Compression.ZipFile]::Open($zip, [IO.Compression.ZipArchiveMode]::Create)
    try {
        foreach ($file in (Get-ChildItem -LiteralPath $package -Recurse -File | Sort-Object FullName)) {
            $entry = $name + '/' + $file.FullName.Substring($package.Length + 1).Replace('\','/')
            [void][IO.Compression.ZipFileExtensions]::CreateEntryFromFile($archive, $file.FullName, $entry, [IO.Compression.CompressionLevel]::Optimal)
        }
    } finally {
        $archive.Dispose()
    }
    $zipHash = (Get-FileHash -LiteralPath $zip -Algorithm SHA256).Hash.ToLowerInvariant()
    Write-Utf8 "$zip.sha256" "$zipHash  $name.zip`n"
    $installedBytes = ($files | Measure-Object -Property size_bytes -Sum).Sum + (Get-Item -LiteralPath (Join-Path $package 'manifest.json')).Length
    Write-Output "ZIP: $zip"
    Write-Output "ZIP bytes: $((Get-Item -LiteralPath $zip).Length); extracted bytes: $installedBytes"
    Write-Output "SHA-256: $zipHash"
} finally {
    Pop-Location
}
