# Probe the real proxy with all 4 Qwen models and write runs\probe_*.json.
# The API key is read hidden and lives only in this process (never saved to disk).
$ErrorActionPreference = "Continue"
$root = Resolve-Path (Join-Path $PSScriptRoot "..\..")
Set-Location $root
$env:PYTHONUTF8 = "1"
$py = Join-Path $root ".venv\Scripts\python.exe"
if (-not (Test-Path $py)) { Write-Host "Run tools\win\setup.cmd first."; Read-Host "Press Enter"; exit 1 }

if (-not $env:LLM_BASE_URL) {
    $u = Read-Host "LLM_BASE_URL (Enter = https://api.neuraldeep.ru/v1)"
    if (-not $u) { $u = "https://api.neuraldeep.ru/v1" }
    $env:LLM_BASE_URL = $u
}
if (-not $env:LLM_API_KEY) {
    $s = Read-Host "LLM_API_KEY (input hidden)" -AsSecureString
    $b = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($s)
    $env:LLM_API_KEY = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($b)
    [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($b)
}
& $py tools\probe_proxy.py @args
Remove-Item Env:\LLM_API_KEY -ErrorAction SilentlyContinue
Read-Host "Done. Press Enter to close"
