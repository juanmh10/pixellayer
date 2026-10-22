[CmdletBinding()]
param([string]$OutputDirectory)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$source = Join-Path $root 'skill\pixellayer'
$versionMatch = [regex]::Match([IO.File]::ReadAllText((Join-Path $root 'Cargo.toml')), '(?m)^version\s*=\s*"([^"]+)"')
if (-not $versionMatch.Success) { throw 'Package version is missing.' }
$version = $versionMatch.Groups[1].Value
$expected = @('SKILL.md', 'SETUP.md', 'config/claude-code.mcp.json', 'config/cursor.mcp.json',
              'config/copilot-vscode.mcp.json', 'config/opencode-v1.mcp.json', 'config/chatgpt-work.mcp.json', 'config/agy.mcp.json', 'config/opencode.mcp.json',
              'config/codex-cli.mcp.toml', 'config/render-config.ps1', 'references/tools.md', 'references/harness-installation.md')
$files = @(Get-ChildItem -LiteralPath $source -Recurse -File)
$relative = @($files | ForEach-Object { $_.FullName.Substring($source.Length + 1).Replace('\','/') })
if (Compare-Object ($expected | Sort-Object) ($relative | Sort-Object)) { throw 'Skill contents differ from the package allowlist.' }
if (@($files | Where-Object { $_.Attributes -band [IO.FileAttributes]::ReparsePoint }).Count) { throw 'Skill files must be regular local files.' }
$skill = [IO.File]::ReadAllText((Join-Path $source 'SKILL.md')).Replace("`r`n", "`n")
if ($skill -notmatch '\A---\nname: pixellayer\ndescription: [^\n]+\n---\n') {
    throw 'Expected a skill entrypoint with name and description frontmatter.'
}
foreach ($name in @('agy', 'opencode', 'opencode-v1', 'chatgpt-work')) {
    $template = Get-Content -LiteralPath (Join-Path $source "config\$name.mcp.json") -Raw -Encoding UTF8 | ConvertFrom-Json
    if ($name -eq 'opencode') {
        if ($template.mcp.servers.pixellayer.type -ne 'local' -or $template.mcp.servers.pixellayer.command[0] -ne '__PIXELLAYER_EXE__') { throw 'Unexpected OpenCode template.' }
    } elseif ($name -eq 'opencode-v1') {
        $entry = $template.mcp.pixellayer
        if ($entry.type -ne 'local' -or $entry.command[0] -ne '__PIXELLAYER_EXE__' -or -not $entry.enabled -or $entry.timeout -ne 120000) { throw 'Unexpected OpenCode v1 template.' }
    } elseif ($name -eq 'chatgpt-work') {
        $entry = $template.mcpServers.pixellayer
        if ($entry.command -ne '__PIXELLAYER_EXE__' -or $entry.args[-1] -ne 'mcp' -or $entry.args[-2] -ne 'fp32' -or $entry.args[-3] -ne '--precision') { throw 'Unexpected ChatGPT Work template.' }
    } elseif ($template.mcpServers.pixellayer.command -ne '__PIXELLAYER_EXE__') { throw 'Unexpected Antigravity template.' }
}
foreach ($name in @('claude-code', 'cursor', 'copilot-vscode')) {
    $template = Get-Content -LiteralPath (Join-Path $source "config\$name.mcp.json") -Raw -Encoding UTF8 | ConvertFrom-Json
    if ($name -eq 'copilot-vscode') { $entry = $template.servers.pixellayer }
    else { $entry = $template.mcpServers.pixellayer }
    if ($entry.type -ne 'stdio' -or $entry.command -ne '__PIXELLAYER_EXE__' -or $entry.args[-1] -ne 'mcp') {
        throw "Unexpected stdio template: $name"
    }
}
if (-not $OutputDirectory) { $OutputDirectory = Join-Path $root 'dist' }
$OutputDirectory = [IO.Path]::GetFullPath($OutputDirectory)
[IO.Directory]::CreateDirectory($OutputDirectory) | Out-Null
$zip = Join-Path $OutputDirectory "pixellayer-skill-$version.zip"
if ((Test-Path -LiteralPath $zip) -or (Test-Path -LiteralPath "$zip.sha256")) { throw 'Skill ZIP already exists. Choose a fresh -OutputDirectory.' }
Add-Type -AssemblyName System.IO.Compression.FileSystem
Add-Type -AssemblyName System.IO.Compression
# Framework ZIP directory helpers can emit backslashes on Windows. Create portable
# entry names explicitly, without a parent directory above SKILL.md.
$archive = [IO.Compression.ZipFile]::Open($zip, [IO.Compression.ZipArchiveMode]::Create)
try {
    foreach ($file in ($files | Sort-Object FullName)) {
        $entry = $file.FullName.Substring($source.Length + 1).Replace('\','/')
        [void][IO.Compression.ZipFileExtensions]::CreateEntryFromFile($archive, $file.FullName, $entry, [IO.Compression.CompressionLevel]::Optimal)
    }
} finally {
    $archive.Dispose()
}
$bytes = (Get-Item -LiteralPath $zip).Length
if ($bytes -gt 50000000) { throw 'Skill ZIP exceeds 50 MB.' }
$hash = (Get-FileHash -LiteralPath $zip -Algorithm SHA256).Hash.ToLowerInvariant()
$utf8 = New-Object Text.UTF8Encoding($false)
[IO.File]::WriteAllText("$zip.sha256", "$hash  $([IO.Path]::GetFileName($zip))`n", $utf8)
Write-Output "Skill ZIP: $zip"
Write-Output "Bytes: $bytes; files: $($files.Count); SKILL.md at root; no engine/runtime/weights."
Write-Output "SHA-256: $hash"
