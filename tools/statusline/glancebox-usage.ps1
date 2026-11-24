# Glance Box usage hook for Claude Code (Windows PowerShell 5.1 or PowerShell 7).
#
# The status-line script runs only in Claude Code's terminal UI. Apps that drive Claude Code
# without it (T3 Code, the desktop app, IDE extensions) still run hooks. As a hook, this script
# fetches the plan limits with `claude -p "/usage"` in the background (about 3 seconds, no
# tokens) and posts the line with the usage report to the Glance Box push inbox. The usage
# report is marked experimental by Anthropic and may change. The script never reads stdin,
# never prints anything and always exits 0 at once. It fetches at most once a minute (the
# stamp file usage.stamp beside push.env; the status-line script writes it too).
# GLANCEBOX_USAGE_TIMEOUT (seconds, default 30) limits the `claude` call.
#
# Settings: %APPDATA%\glancebox\push.env with the lines
#   GLANCEBOX_URL=http://192.168.1.10:8080
#   GLANCEBOX_PUSH_KEY=<the push_key of the server>
#
# %USERPROFILE%\.claude\settings.json (forward slashes: Claude Code may run the command
# through Git Bash):
#   "hooks": {
#     "Stop": [{"hooks": [{"type": "command", "command":
#       "powershell -NoProfile -ExecutionPolicy Bypass -File C:/path/to/glancebox-usage.ps1"}]}],
#     "PostToolUse": [{"hooks": [{"type": "command", "command":
#       "powershell -NoProfile -ExecutionPolicy Bypass -File C:/path/to/glancebox-usage.ps1"}]}]
#   }

$ErrorActionPreference = 'SilentlyContinue'

# The `claude` call below runs hooks too, this one included.
if ($env:GLANCEBOX_USAGE -eq '1') { exit 0 }

$url = ''
$key = ''
if (-not $env:APPDATA) { exit 0 }
$dir = Join-Path $env:APPDATA 'glancebox'
$envFile = Join-Path $dir 'push.env'
if (Test-Path -LiteralPath $envFile) {
    foreach ($line in Get-Content -LiteralPath $envFile) {
        $name, $value = $line -split '=', 2
        switch ($name.Trim()) {
            'GLANCEBOX_URL' { $url = "$value".Trim() }
            'GLANCEBOX_PUSH_KEY' { $key = "$value".Trim() }
        }
    }
}
if (-not ($url -and $key)) { exit 0 }

# The stamp is opened exclusively, so check and write are one step and two hooks that fire
# together fetch once (the second cannot open it and leaves).
try {
    $now = [DateTimeOffset]::UtcNow.ToUnixTimeSeconds()
    $stream = [IO.File]::Open((Join-Path $dir 'usage.stamp'), 'OpenOrCreate', 'ReadWrite', 'None')
    try {
        $bytes = New-Object byte[] 64
        $count = $stream.Read($bytes, 0, $bytes.Length)
        $last = [Text.Encoding]::ASCII.GetString($bytes, 0, $count).Trim()
        # Only plain epoch seconds count, as in the .sh script; anything else means fetch.
        if ($last -match '^[1-9][0-9]{0,11}$') {
            $age = $now - [long]$last
            if ($age -ge 0 -and $age -lt 60) { exit 0 }
        }
        $text = [Text.Encoding]::ASCII.GetBytes("$now`n")
        $stream.SetLength(0)
        $stream.Write($text, 0, $text.Length)
    } finally {
        $stream.Close()
    }
} catch {
    exit 0
}

$timeout = "$env:GLANCEBOX_USAGE_TIMEOUT"
if ($timeout -notmatch '^[1-9][0-9]*$') { $timeout = '30' }

# A separate hidden PowerShell process does the fetch and the request, so the hook returns
# at once (a Start-Job would be stopped when this script exits) and the hook runner never
# waits for it. The values go through the environment, so the key does not appear on a
# command line.
$request = @'
try {
    $env:GLANCEBOX_USAGE = '1'
    Set-Location -LiteralPath $env:GLANCEBOX_USAGE_DIR
    $claude = Get-Command claude -CommandType Application | Select-Object -First 1
    if (-not $claude) { exit 0 }
    $info = New-Object Diagnostics.ProcessStartInfo
    $info.FileName = $claude.Source
    $info.Arguments = '-p "/usage" --output-format stream-json --verbose --no-session-persistence'
    $info.UseShellExecute = $false
    $info.CreateNoWindow = $true
    $info.RedirectStandardInput = $true
    $info.RedirectStandardOutput = $true
    $info.RedirectStandardError = $true
    $info.StandardOutputEncoding = [Text.Encoding]::UTF8
    $process = [Diagnostics.Process]::Start($info)
    $process.StandardInput.Close()
    $out = $process.StandardOutput.ReadToEndAsync()
    $null = $process.StandardError.ReadToEndAsync()
    if (-not $process.WaitForExit([int]$env:GLANCEBOX_USAGE_TIMEOUT * 1000)) {
        # The whole tree: an npm install starts claude through a .cmd wrapper.
        & taskkill.exe /T /F /PID $process.Id | Out-Null
        exit 0
    }
    $line = $out.Result -split "`n" | ForEach-Object { $_.TrimEnd("`r") } |
        Where-Object { $_.Contains('"usage_report"') -and $_ -match '"limits":\[[^\]]' } |
        Select-Object -First 1
    if ($line) {
        Invoke-RestMethod -Method Post -Uri $env:GLANCEBOX_PUSH_URI `
            -Headers @{ Authorization = "Bearer $env:GLANCEBOX_PUSH_KEY" } `
            -ContentType 'application/json' -TimeoutSec 5 `
            -Body ([Text.Encoding]::UTF8.GetBytes($line)) | Out-Null
    }
} catch {}
'@
try {
    $env:GLANCEBOX_PUSH_URI = $url.TrimEnd('/') + '/api/v1/push/claude'
    $env:GLANCEBOX_PUSH_KEY = $key
    $env:GLANCEBOX_USAGE_DIR = $dir
    $env:GLANCEBOX_USAGE_TIMEOUT = $timeout
    $encoded = [Convert]::ToBase64String([Text.Encoding]::Unicode.GetBytes($request))
    $shell = (Get-Process -Id $PID).Path
    Start-Process -FilePath $shell -WindowStyle Hidden `
        -ArgumentList '-NoProfile', '-NonInteractive', '-EncodedCommand', $encoded
} catch {}
exit 0
