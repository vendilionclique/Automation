$ErrorActionPreference = "Stop"

Write-Warning "Windows Codex sync is retained for future/experimental use. The current Taobao visual collection mainline is macOS; use scripts/sync_agent_project_config.sh there."

$RootDir = Resolve-Path (Join-Path $PSScriptRoot "..")
$CodexHome = if ($env:CODEX_HOME) { $env:CODEX_HOME } else { Join-Path $HOME ".codex" }
$CodexConfig = Join-Path $CodexHome "config.toml"
$McpLauncher = Join-Path $RootDir "scripts\start_midscene_computer_mcp.ps1"
$LocalEnv = Join-Path $RootDir "local\midscene-computer.env"

New-Item -ItemType Directory -Force -Path $CodexHome | Out-Null
if (-not (Test-Path -LiteralPath $CodexConfig)) {
    New-Item -ItemType File -Force -Path $CodexConfig | Out-Null
}

$configText = Get-Content -LiteralPath $CodexConfig -Raw -Encoding UTF8
$MidsceneAllowedTools = @(
    "ListDisplays",
    "computer_connect",
    "computer_disconnect",
    "computer_list_displays",
    "take_screenshot",
    "act"
)

$toolBlocks = ($MidsceneAllowedTools | ForEach-Object {
@"
[mcp_servers.midscene-computer.tools.$_]
approval_mode = "approve"

"@
}) -join ""

$serverBlock = @"
[mcp_servers.midscene-computer]
command = "powershell"
args = ["-NoProfile", "-ExecutionPolicy", "Bypass", "-File", "$($McpLauncher -replace '\\', '\\')"]
enabled = true
startup_timeout_sec = 30
tool_timeout_sec = 180

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

$profileBlock = @"
[profiles.taobao_visual_cron]
model = "gpt-5.5"
sandbox_mode = "danger-full-access"
approval_policy = "never"
cwd = "$($RootDir -replace '\\', '\\')"

"@

$profilePattern = '(?ms)^\[profiles\.taobao_visual_cron\]\r?\n.*?(?=^\[|\z)'
if ($configText -match $profilePattern) {
    $configText = [regex]::Replace($configText, $profilePattern, $profileBlock)
} else {
    if ($configText.Length -gt 0 -and -not $configText.EndsWith("`n")) {
        $configText += "`n"
    }
    $configText += "`n" + $profileBlock
}

$extractProfileBlock = @"
[profiles.taobao_visual_extract]
model = "gpt-5.5"
sandbox_mode = "danger-full-access"
approval_policy = "never"
cwd = "$($RootDir -replace '\\', '\\')"

"@

$extractProfilePattern = '(?ms)^\[profiles\.taobao_visual_extract\]\r?\n.*?(?=^\[|\z)'
if ($configText -match $extractProfilePattern) {
    $configText = [regex]::Replace($configText, $extractProfilePattern, $extractProfileBlock)
} else {
    if ($configText.Length -gt 0 -and -not $configText.EndsWith("`n")) {
        $configText += "`n"
    }
    $configText += "`n" + $extractProfileBlock
}

if ($env:CODEX_SET_DEFAULT_TAOBAO_VISUAL_CRON) {
    $defaultLines = [ordered]@{
        "model" = 'model = "gpt-5.5"'
        "sandbox_mode" = 'sandbox_mode = "danger-full-access"'
        "approval_policy" = 'approval_policy = "never"'
    }
    foreach ($entry in $defaultLines.GetEnumerator()) {
        $keyPattern = "(?m)^$([regex]::Escape($entry.Key))\s*=.*$"
        if ($configText -match $keyPattern) {
            $configText = [regex]::Replace($configText, $keyPattern, $entry.Value, 1)
        } else {
            $configText = $entry.Value + "`n" + $configText
        }
    }
}
$utf8NoBom = New-Object System.Text.UTF8Encoding($false)
[System.IO.File]::WriteAllText($CodexConfig, $configText, $utf8NoBom)

if (-not (Test-Path -LiteralPath $LocalEnv)) {
    New-Item -ItemType Directory -Force -Path (Split-Path $LocalEnv) | Out-Null
    $runDir = (Join-Path $RootDir "local\midscene-run") -replace '\\', '/'
    @"
# Local Midscene computer VLM config. Gitignored; do not commit.
export MIDSCENE_MODEL_NAME="glm-4.6v-flashx"
export MIDSCENE_MODEL_API_KEY=""
export MIDSCENE_MODEL_BASE_URL="https://open.bigmodel.cn/api/paas/v4"
export MIDSCENE_MODEL_FAMILY="glm-v"
export MIDSCENE_MODEL_REASONING_ENABLED="false"
export MIDSCENE_MODEL_TEMPERATURE="0"
export MIDSCENE_RUN_DIR="$runDir"
export MIDSCENE_REPORT_QUIET="true"
"@ | Set-Content -LiteralPath $LocalEnv -Encoding UTF8
}

Write-Host "Codex MCP configured: $CodexConfig"
Write-Host "Codex cron profile configured: taobao_visual_cron"
Write-Host "Codex extract profile configured: taobao_visual_extract"
Write-Host "Project skill remains repo-local: $(Join-Path $RootDir '.agents\skills\taobao-visual-collection')"
Write-Host "Midscene env file: $LocalEnv"
Write-Host "Cursor project MCP config is tracked at .cursor/mcp.json"
