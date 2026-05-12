$ErrorActionPreference = "Stop"

$RootDir = Resolve-Path (Join-Path $PSScriptRoot "..")
$EnvFile = if ($env:MIDSCENE_ENV_FILE) { $env:MIDSCENE_ENV_FILE } else { Join-Path $RootDir "local\midscene-computer.env" }
$Launcher = Join-Path $RootDir "scripts\midscene_computer_mcp_launcher.cjs"

if (Test-Path -LiteralPath $EnvFile) {
    Get-Content -LiteralPath $EnvFile -Encoding UTF8 | ForEach-Object {
        $line = $_.Trim()
        if (-not $line -or $line.StartsWith("#")) { return }
        if ($line.StartsWith("export ")) {
            $line = $line.Substring(7).Trim()
        }
        $parts = $line.Split("=", 2)
        if ($parts.Count -ne 2) { return }
        $name = $parts[0].Trim()
        $value = $parts[1].Trim().Trim('"').Trim("'")
        if ($name) {
            Set-Item -Path "Env:$name" -Value $value
        }
    }
}

if (-not $env:MIDSCENE_RUN_DIR) {
    $env:MIDSCENE_RUN_DIR = Join-Path $RootDir "local\midscene-run"
}
if (-not $env:MIDSCENE_REPORT_QUIET) {
    $env:MIDSCENE_REPORT_QUIET = "true"
}

& node $Launcher @args
exit $LASTEXITCODE
