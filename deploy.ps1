$ErrorActionPreference = 'Stop'
$python = Get-Command python -ErrorAction SilentlyContinue
if (-not $python) { throw 'Python 3.10+ is required. Install Python, then rerun deploy.ps1.' }
& $python.Source (Join-Path $PSScriptRoot 'scripts\deploy.py') @args
exit $LASTEXITCODE
