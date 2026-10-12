$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root
$env:DEMO_DELAY_MS = '0'
python -m uvicorn src.explainer_agent:app --host 127.0.0.1 --port 8002
