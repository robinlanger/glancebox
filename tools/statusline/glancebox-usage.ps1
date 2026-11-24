# Glance Box usage hook for Claude Code (Windows PowerShell 5.1 or PowerShell 7).
#
# The status-line script runs only in Claude Code's terminal UI. Apps that drive Claude Code
# without it (T3 Code, the desktop app, IDE extensions) still run hooks. As a hook, this script
# fetches the plan limits with `claude -p "/usage"` in the background (about 3 seconds, no
# tokens) and posts the line with the usage report to the Glance Box push inbox. The usage
# report is marked experimental by Anthropic and may change. The script never reads stdin,
# never prints anything and always exits 0 at once. It fetches at most once a minute (the
# stamp file usage.stamp beside push.env; the status-line script writes it too). A hook
# inside that minute leaves one fetch waiting for its end (marker usage.pending), so the last
# answer of a burst reaches the display too; that fetch is dropped if the stamp changes first.
# GLANCEBOX_USAGE_TIMEOUT (seconds, default 30) limits the `claude` call.
# GLANCEBOX_USAGE_THROTTLE (seconds, default 60) is a knob for the tests only.
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

$throttle = "$env:GLANCEBOX_USAGE_THROTTLE"
if ($throttle -notmatch '^[1-9][0-9]{0,5}$') { $throttle = '60' }
$throttle = [long]$throttle
$pending = Join-Path $dir 'usage.pending'
$wait = 0
$last = ''

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
            if ($age -ge 0 -and $age -lt $throttle) {
                # Too soon. One fetch waits for the end of the window, so the last answer of a
                # burst is sent too; if one waits already, this hook is covered. CreateNew
                # fails when the marker exists; one left by a killed run counts after two
                # minutes.
                try {
                    $marker = [IO.File]::Open($pending, 'CreateNew', 'Write', 'None')
                } catch {
                    $item = Get-Item -LiteralPath $pending
                    $stale = [DateTime]::UtcNow.AddMinutes(-2)
                    if (-not $item -or $item.LastWriteTimeUtc -gt $stale) { exit 0 }
                    Remove-Item -LiteralPath $pending -Force
                    $marker = [IO.File]::Open($pending, 'CreateNew', 'Write', 'None')
                }
                $marker.Close()
                $wait = $throttle - $age
            }
        }
        if ($wait -eq 0) {
            $text = [Text.Encoding]::ASCII.GetBytes("$now`n")
            $stream.SetLength(0)
            $stream.Write($text, 0, $text.Length)
        }
    } finally {
        $stream.Close()
    }
} catch {
    exit 0
}

$timeout = "$env:GLANCEBOX_USAGE_TIMEOUT"
# 1 to 999999 seconds; anything else means the default.
if ($timeout -notmatch '^[1-9][0-9]{0,5}$') { $timeout = '30' }

# A separate hidden PowerShell process does the fetch and the request, so the hook returns
# at once (a Start-Job would be stopped when this script exits) and the hook runner never
# waits for it. The values go through the environment, so the key does not appear on a
# command line. For a waiting fetch the same process first sleeps until the window ends.
$request = @'
try {
    # The key and the address stay in this process; claude and what it starts never see them.
    $uri = $env:GLANCEBOX_PUSH_URI
    $key = $env:GLANCEBOX_PUSH_KEY
    $wait = [int]$env:GLANCEBOX_USAGE_WAIT
    $seen = $env:GLANCEBOX_USAGE_LAST
    Remove-Item -Path Env:GLANCEBOX_PUSH_KEY, Env:GLANCEBOX_PUSH_URI
    Remove-Item -Path Env:GLANCEBOX_USAGE_WAIT, Env:GLANCEBOX_USAGE_LAST
    $env:GLANCEBOX_USAGE = '1'
    Set-Location -LiteralPath $env:GLANCEBOX_USAGE_DIR
    if ($wait -gt 0) {
        Start-Sleep -Seconds $wait
        Remove-Item -LiteralPath (Join-Path $env:GLANCEBOX_USAGE_DIR 'usage.pending') -Force
        # Fetch only if the stamp is unchanged: a new one means newer data was sent meanwhile
        # (status line or another fetch). Opened exclusively as in the hook; when another
        # hook holds it, that one decides.
        $stream = [IO.File]::Open((Join-Path $env:GLANCEBOX_USAGE_DIR 'usage.stamp'),
            'OpenOrCreate', 'ReadWrite', 'None')
        try {
            $bytes = New-Object byte[] 64
            $count = $stream.Read($bytes, 0, $bytes.Length)
            if ([Text.Encoding]::ASCII.GetString($bytes, 0, $count).Trim() -ne $seen) { exit 0 }
            $now = [DateTimeOffset]::UtcNow.ToUnixTimeSeconds()
            $text = [Text.Encoding]::ASCII.GetBytes("$now`n")
            $stream.SetLength(0)
            $stream.Write($text, 0, $text.Length)
        } finally {
            $stream.Close()
        }
    }
    $claude = Get-Command claude -CommandType Application | Select-Object -First 1
    if (-not $claude) { exit 0 }
    $info = New-Object Diagnostics.ProcessStartInfo
    $info.FileName = $claude.Path
    $info.Arguments = '-p "/usage" --output-format stream-json --verbose --no-session-persistence'
    # Set-Location does not change the directory that .NET starts processes in.
    $info.WorkingDirectory = $env:GLANCEBOX_USAGE_DIR
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
        Invoke-RestMethod -Method Post -Uri $uri `
            -Headers @{ Authorization = "Bearer $key" } `
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
    $env:GLANCEBOX_USAGE_WAIT = "$wait"
    $env:GLANCEBOX_USAGE_LAST = $last
    $encoded = [Convert]::ToBase64String([Text.Encoding]::Unicode.GetBytes($request))
    $shell = (Get-Process -Id $PID).Path
    Start-Process -FilePath $shell -WindowStyle Hidden `
        -WorkingDirectory $dir `
        -ArgumentList '-NoProfile', '-NonInteractive', '-EncodedCommand', $encoded
} catch {}
exit 0
