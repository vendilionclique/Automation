$ErrorActionPreference = "Stop"

$RootDir = Resolve-Path (Join-Path $PSScriptRoot "..")
$ProfileDir = if ($env:TAOBAO_CHROME_PROFILE_DIR) {
    $env:TAOBAO_CHROME_PROFILE_DIR
} else {
    Join-Path $RootDir "local\chrome-taobao-visual-profile"
}
$StartUrl = if ($env:TAOBAO_START_URL) { $env:TAOBAO_START_URL } else { "https://www.taobao.com/" }
$WindowWidth = if ($env:TAOBAO_WINDOW_WIDTH) { [int]$env:TAOBAO_WINDOW_WIDTH } else { 1600 }
$WindowHeight = if ($env:TAOBAO_WINDOW_HEIGHT) { [int]$env:TAOBAO_WINDOW_HEIGHT } else { 1000 }
$WindowX = if ($env:TAOBAO_WINDOW_X) { [int]$env:TAOBAO_WINDOW_X } else { 0 }
$WindowY = if ($env:TAOBAO_WINDOW_Y) { [int]$env:TAOBAO_WINDOW_Y } else { 0 }

New-Item -ItemType Directory -Force -Path $ProfileDir | Out-Null
$resolvedProfile = (Resolve-Path -LiteralPath $ProfileDir).Path

function Get-ChromePath {
    $candidates = @(
        $env:CHROME_BIN,
        "$env:ProgramFiles\Google\Chrome\Application\chrome.exe",
        "${env:ProgramFiles(x86)}\Google\Chrome\Application\chrome.exe",
        "$env:LocalAppData\Google\Chrome\Application\chrome.exe"
    ) | Where-Object { $_ }
    foreach ($candidate in $candidates) {
        if (Test-Path -LiteralPath $candidate) {
            return $candidate
        }
    }
    throw "Chrome executable not found. Set CHROME_BIN to chrome.exe."
}

function Get-ProfileChromeProcesses {
    $escaped = [regex]::Escape($resolvedProfile)
    Get-CimInstance Win32_Process -Filter "name = 'chrome.exe'" |
        Where-Object { $_.CommandLine -match "--user-data-dir=`"?$escaped`"?" }
}

function Focus-Chrome {
    param([int[]]$ProcessIds)

    Add-Type @"
using System;
using System.Runtime.InteropServices;
public class Win32Window {
  [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr hWnd);
  [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr hWnd, int nCmdShow);
}
"@

    foreach ($processId in $ProcessIds) {
        $process = Get-Process -Id $processId -ErrorAction SilentlyContinue
        if ($process -and $process.MainWindowHandle -ne 0) {
            [Win32Window]::ShowWindow($process.MainWindowHandle, 9) | Out-Null
            [Win32Window]::SetForegroundWindow($process.MainWindowHandle) | Out-Null
            return $true
        }
    }

    $chromeWindow = Get-Process chrome -ErrorAction SilentlyContinue |
        Where-Object { $_.MainWindowHandle -ne 0 } |
        Select-Object -First 1
    if ($chromeWindow) {
        [Win32Window]::ShowWindow($chromeWindow.MainWindowHandle, 9) | Out-Null
        [Win32Window]::SetForegroundWindow($chromeWindow.MainWindowHandle) | Out-Null
        return $true
    }
    return $false
}

$existing = @(Get-ProfileChromeProcesses)
if ($existing.Count -gt 0) {
    $focused = Focus-Chrome -ProcessIds ($existing | ForEach-Object { [int]$_.ProcessId })
    Write-Host "Taobao visual Chrome is already running with profile: $resolvedProfile"
    Write-Host "Foreground focus attempted: $focused"
    exit 0
}

$chrome = Get-ChromePath
$args = @(
    "--user-data-dir=$resolvedProfile",
    "--profile-directory=Default",
    "--no-first-run",
    "--no-default-browser-check",
    "--disable-features=Translate",
    "--new-window",
    "--window-position=$WindowX,$WindowY",
    "--window-size=$WindowWidth,$WindowHeight",
    $StartUrl
)

Start-Process -FilePath $chrome -ArgumentList $args -WindowStyle Normal
Start-Sleep -Seconds 2
$launched = @(Get-ProfileChromeProcesses)
if ($launched.Count -gt 0) {
    Focus-Chrome -ProcessIds ($launched | ForEach-Object { [int]$_.ProcessId }) | Out-Null
}
Write-Host "Started Taobao visual Chrome with profile: $resolvedProfile"
