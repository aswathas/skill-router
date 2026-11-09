$ErrorActionPreference = 'SilentlyContinue'
param([string]$Event = '')
if (-not $Event) { $Event = $args[0] }
$script = Join-Path $PSScriptRoot 'learning-hook.py'
$payload = [Console]::In.ReadToEnd()
$tmp = [System.IO.Path]::GetTempFileName()
[System.IO.File]::WriteAllText($tmp, $payload)
try {
  python $script --event $Event --payload-file $tmp | Out-Null
} catch { }
finally {
  Remove-Item $tmp -Force -ErrorAction SilentlyContinue
}
exit 0
