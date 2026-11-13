# One-time setup on Windows: Python 3.12 venv with pinned openJiuwen 0.1.19.
# Run:  double-click tools\win\setup.cmd   (or: powershell -ExecutionPolicy Bypass -File tools\win\setup.ps1)
$ErrorActionPreference = "Continue"
$root = Resolve-Path (Join-Path $PSScriptRoot "..\..")
Set-Location $root
$env:PYTHONUTF8 = "1"

function Test-Py($v) {
    try { & py "-$v" -c "import sys" 2>$null | Out-Null; return ($LASTEXITCODE -eq 0) } catch { return $false }
}

$ver = $null
foreach ($v in @("3.12", "3.13", "3.11")) { if (Test-Py $v) { $ver = $v; break } }
if (-not $ver) {
    Write-Host "Python 3.11-3.13 not found (openJiuwen does not support 3.14). Installing Python 3.12..."
    try { & py install 3.12 } catch { }
    if (-not (Test-Py "3.12")) {
        winget install -e --id Python.Python.3.12 --accept-source-agreements --accept-package-agreements
    }
    if (Test-Py "3.12") { $ver = "3.12" } else {
        Write-Host "Could not install Python 3.12 automatically. Install it from python.org and rerun."
        Read-Host "Press Enter to exit"; exit 1
    }
}
Write-Host "Using Python $ver"
if (-not (Test-Path ".venv\Scripts\python.exe")) { & py "-$ver" -m venv .venv }
$py = Join-Path $root ".venv\Scripts\python.exe"
& $py -m pip install --upgrade pip
& $py -m pip install -r requirements.txt -c constraints.txt
if ($LASTEXITCODE -ne 0) {
    Write-Host "Pinned install failed on this platform; retrying without constraints..."
    & $py -m pip install -r requirements.txt
}
& $py tools/selfcheck.py --api-only
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
Write-Host "For the offline sample run, use tools\win\docker_check.cmd in Linux container mode."
Write-Host ""
Write-Host "Setup finished. Next: double-click tools\win\probe.cmd"
Read-Host "Press Enter to close"
