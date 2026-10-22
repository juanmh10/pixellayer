[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$Executable,
    [Parameter(Mandatory = $true)][string]$Workspace,
    [Parameter(Mandatory = $true)][string]$CacheDirectory,
    [Parameter(Mandatory = $true)][string]$OutputDirectory,
    [ValidateSet('Windows', 'WSL')][string]$AgentPlatform = 'Windows'
)

# Optional attachment. Generates drafts only; never edits an agent configuration.
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
foreach ($path in @($Executable, $Workspace, $CacheDirectory, $OutputDirectory)) {
    if (-not [IO.Path]::IsPathRooted($path)) { throw 'Use absolute Windows paths for all four parameters.' }
}
$Executable = (Resolve-Path -LiteralPath $Executable).Path
$Workspace = (Resolve-Path -LiteralPath $Workspace).Path
if (-not (Test-Path -LiteralPath $Executable -PathType Leaf)) { throw 'Executable is not a file.' }
if (-not (Test-Path -LiteralPath $Workspace -PathType Container)) { throw 'Workspace is not a directory.' }
$runtime = Join-Path (Split-Path -Parent $Executable) 'onnxruntime.dll'
if (-not (Test-Path -LiteralPath $runtime -PathType Leaf)) { throw 'Use the packaged executable with onnxruntime.dll beside it.' }
$CacheDirectory = [IO.Path]::GetFullPath($CacheDirectory)
$launcher = $Executable
if ($AgentPlatform -eq 'WSL') {
    if ($Executable -notmatch '^([A-Za-z]):\\(.*)$') { throw 'WSL launch requires a package on a mounted Windows drive.' }
    $launcher = '/mnt/' + $Matches[1].ToLowerInvariant() + '/' + $Matches[2].Replace('\', '/')
}
$values = @{
    '__PIXELLAYER_EXE__' = $launcher
    '__PIXELLAYER_WORKSPACE__' = $Workspace.Replace('\', '/')
    '__PIXELLAYER_CACHE__' = $CacheDirectory.Replace('\', '/')
    '__PIXELLAYER_RUNTIME__' = $runtime.Replace('\', '/')
}
if (Test-Path -LiteralPath $CacheDirectory -PathType Leaf) { throw 'Cache path is an existing file.' }
$OutputDirectory = [IO.Path]::GetFullPath($OutputDirectory)
if (Test-Path -LiteralPath $OutputDirectory) { throw 'Draft output directory must be new; existing files are never replaced.' }
$utf8 = New-Object Text.UTF8Encoding($false)
$staging = $null
try {
    $parent = Split-Path -Parent $OutputDirectory
    [IO.Directory]::CreateDirectory($parent) | Out-Null
    $staging = Join-Path $parent ('.pixellayer-config-' + [guid]::NewGuid().ToString('N'))
    [IO.Directory]::CreateDirectory($staging) | Out-Null
    foreach ($file in @('claude-code.mcp.json', 'cursor.mcp.json', 'copilot-vscode.mcp.json',
                        'agy.mcp.json', 'opencode.mcp.json', 'opencode-v1.mcp.json', 'codex-cli.mcp.toml', 'chatgpt-work.mcp.json')) {
        $text = [IO.File]::ReadAllText((Join-Path $PSScriptRoot $file))
        foreach ($token in $values.Keys) {
            $text = $text.Replace(('"' + $token + '"'), (ConvertTo-Json -InputObject $values[$token] -Compress))
        }
        if ($file.EndsWith('.json')) { $null = $text | ConvertFrom-Json }
        [IO.File]::WriteAllText((Join-Path $staging $file), $text, $utf8)
    }
    [IO.Directory]::Move($staging, $OutputDirectory)
    Write-Output "Eight configuration drafts (seven clients; two OpenCode formats) written to $OutputDirectory (agent platform: $AgentPlatform)"
    Write-Output 'Review and merge only the selected PixelLayer entry into the chosen agent. Nothing was installed or configured.'
} finally {
    if ($staging -and (Test-Path -LiteralPath $staging)) { Remove-Item -LiteralPath $staging -Recurse -Force }
}
