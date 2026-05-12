$ErrorActionPreference = "Stop"

$RootDir = Resolve-Path (Join-Path $PSScriptRoot "..")
$CodexHome = if ($env:CODEX_HOME) { $env:CODEX_HOME } else { Join-Path $HOME ".codex" }
$CodexConfig = Join-Path $CodexHome "config.toml"
$SkillSource = Join-Path $RootDir ".agents\skills\taobao-visual-collection"
$SkillTarget = Join-Path $CodexHome "skills\taobao-visual-collection"
$McpLauncher = Join-Path $RootDir "scripts\start_midscene_computer_mcp.ps1"
$LocalEnv = Join-Path $RootDir "local\midscene-computer.env"

New-Item -ItemType Directory -Force -Path $CodexHome | Out-Null
if (-not (Test-Path -LiteralPath $CodexConfig)) {
    New-Item -ItemType File -Force -Path $CodexConfig | Out-Null
}

$configText = Get-Content -LiteralPath $CodexConfig -Raw -Encoding UTF8
$MidsceneAllowedTools = @(
    "computer_list_displays",
    "ListDisplays",
    "computer_connect",
    "computer_disconnect",
    "take_screenshot",
    "Tap",
    "Input",
    "ClearInput",
    "KeyboardPress",
    "Scroll",
    "MouseMove",
    "DoubleClick",
    "RightClick",
    "DragAndDrop",
    "act",
    "assert"
)

$toolBlocks = ($MidsceneAllowedTools | ForEach-Object {
@"
[mcp_servers.midscene-computer.tools.$_]
approval_mode = "never"

"@
}) -join ""

$serverBlock = @"
[mcp_servers.midscene-computer]
command = "powershell"
args = ["-NoProfile", "-ExecutionPolicy", "Bypass", "-File", "$($McpLauncher -replace '\\', '\\')"]
enabled = true

$toolBlocks
"@

$pattern = '(?ms)^\[mcp_servers\.midscene-computer\]\r?\n.*?(?=^\[(?!mcp_servers\.midscene-computer(?:\.tools\.)?)|\z)'
if ($configText -match $pattern) {
    $configText = [regex]::Replace($configText, $pattern, $serverBlock)
} else {
    if ($configText.Length -gt 0 -and -not $configText.EndsWith("`n")) {
        $configText += "`n"
    }
    $configText += "`n" + $serverBlock
}
$utf8NoBom = New-Object System.Text.UTF8Encoding($false)
[System.IO.File]::WriteAllText($CodexConfig, $configText, $utf8NoBom)

if (Test-Path -LiteralPath $SkillSource) {
    New-Item -ItemType Directory -Force -Path (Split-Path $SkillTarget) | Out-Null
    if (Test-Path -LiteralPath $SkillTarget) {
        $resolvedCodexSkills = [System.IO.Path]::GetFullPath((Join-Path $CodexHome "skills"))
        $resolvedSkillTarget = [System.IO.Path]::GetFullPath($SkillTarget)
        if (-not $resolvedSkillTarget.StartsWith($resolvedCodexSkills, [System.StringComparison]::OrdinalIgnoreCase)) {
            throw "Refusing to remove unexpected skill target: $resolvedSkillTarget"
        }
        Remove-Item -LiteralPath $SkillTarget -Recurse -Force
    }
    Copy-Item -LiteralPath $SkillSource -Destination $SkillTarget -Recurse -Force
}

if (-not (Test-Path -LiteralPath $LocalEnv)) {
    New-Item -ItemType Directory -Force -Path (Split-Path $LocalEnv) | Out-Null
    $runDir = (Join-Path $RootDir "local\midscene-run") -replace '\\', '/'
    @"
# Local Midscene computer VLM config. Gitignored; do not commit.
export MIDSCENE_MODEL_NAME="glm-5v-turbo"
export MIDSCENE_MODEL_API_KEY=""
export MIDSCENE_MODEL_BASE_URL="https://open.bigmodel.cn/api/paas/v4"
export MIDSCENE_MODEL_FAMILY="glm-v"
export MIDSCENE_MODEL_REASONING_ENABLED="false"
export MIDSCENE_RUN_DIR="$runDir"
export MIDSCENE_REPORT_QUIET="true"
"@ | Set-Content -LiteralPath $LocalEnv -Encoding UTF8
}

Write-Host "Codex MCP configured: $CodexConfig"
Write-Host "Codex project skill synced: $SkillTarget"
Write-Host "Midscene env file: $LocalEnv"
Write-Host "Cursor project MCP config is tracked at .cursor/mcp.json"
