# Glance Box status-line script for Claude Code (Windows PowerShell 5.1 or PowerShell 7).
#
# Claude Code passes its status-line JSON on stdin. This script posts it in the background
# to the Glance Box push inbox (the server keeps only `rate_limits` and drops the rest) and
# never prints errors. Arguments, if given, are your existing status-line command: it gets
# the same stdin and its output and exit status become the status line.
#
# Settings: %APPDATA%\glancebox\push.env with the lines
#   GLANCEBOX_URL=http://192.168.1.10:8080
#   GLANCEBOX_PUSH_KEY=<the push_key of the server>
#
# %USERPROFILE%\.claude\settings.json:
#   "statusLine": {"type": "command",
#     "command": "powershell -NoProfile -ExecutionPolicy Bypass -File C:/path/to/glancebox-statusline.ps1"}
#   (forward slashes: Claude Code may run the command through Git Bash)

$ErrorActionPreference = 'SilentlyContinue'
[Console]::InputEncoding = [Text.Encoding]::UTF8
# UTF-8 for the status-line output and for text piped to a wrapped command (PowerShell 5.1).
$OutputEncoding = [Console]::OutputEncoding = [Text.Encoding]::UTF8
$inputText = [Console]::In.ReadToEnd()

$url = ''
$key = ''
$envFile = Join-Path $env:APPDATA 'glancebox\push.env'
if ($env:APPDATA -and (Test-Path -LiteralPath $envFile)) {
    foreach ($line in Get-Content -LiteralPath $envFile) {
        $name, $value = $line -split '=', 2
        switch ($name.Trim()) {
            'GLANCEBOX_URL' { $url = "$value".Trim() }
            'GLANCEBOX_PUSH_KEY' { $key = "$value".Trim() }
        }
    }
}

# Before the first answer of a session the JSON has no rate_limits yet; sending it would
# replace the last good values on the display with nothing.
if ($url -and $key -and $inputText.Contains('"rate_limits"')) {
    try {
        # A separate hidden PowerShell process does the request, so the status line never
        # waits for it (a Start-Job would be stopped when this script exits). The values go
        # through the environment, so the key does not appear on a command line.
        $env:GLANCEBOX_PUSH_URI = $url.TrimEnd('/') + '/api/v1/push/claude'
        $env:GLANCEBOX_PUSH_KEY = $key
        $env:GLANCEBOX_PUSH_BODY = $inputText
        $request = 'try { Invoke-RestMethod -Method Post -Uri $env:GLANCEBOX_PUSH_URI ' +
            '-Headers @{ Authorization = "Bearer $env:GLANCEBOX_PUSH_KEY" } ' +
            '-ContentType "application/json" -TimeoutSec 2 ' +
            '-Body ([Text.Encoding]::UTF8.GetBytes($env:GLANCEBOX_PUSH_BODY)) | Out-Null } catch {}'
        $encoded = [Convert]::ToBase64String([Text.Encoding]::Unicode.GetBytes($request))
        $shell = (Get-Process -Id $PID).Path
        Start-Process -FilePath $shell -WindowStyle Hidden `
            -ArgumentList '-NoProfile', '-NonInteractive', '-EncodedCommand', $encoded
    } catch {}
    # The usage hook (glancebox-usage.ps1) skips its fetch for a minute after this.
    try {
        [IO.File]::WriteAllText((Join-Path $env:APPDATA 'glancebox\usage.stamp'),
            "$([DateTimeOffset]::UtcNow.ToUnixTimeSeconds())`n")
    } catch {}
}

if ($args.Count -gt 0) {
    $command = $args[0]
    $rest = @($args | Select-Object -Skip 1)
    $inputText | & $command @rest
    exit $LASTEXITCODE
}
exit 0
