# Small real run of the whole harness (step 2, after probe.cmd):
# 12 generated tasks, deterministic solvers switched OFF so every task goes
# through real Qwen, hard budget 6000 competition tokens (override: $env:SMOKE_BUDGET).
# Writes runs\smoke_<time>\ (tasks, answers, trace.json, score.txt). No secrets are saved.
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
$budget = if ($env:SMOKE_BUDGET) { $env:SMOKE_BUDGET } else { "6000" }
$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$run = Join-Path $root "runs\smoke_$stamp"
New-Item -ItemType Directory -Force $run | Out-Null
$tasks = Join-Path $run "tasks"
& $py tools\task_factory.py $tasks --n 12 --seed 7 --infeasible 0.2
$env:BUDGET = $budget
$env:HARNESS_DISABLE_DET = "math,search,data_analysis,coding"
$env:HARNESS_TRACE = Join-Path $run "trace.json"
$env:HARNESS_TIME_LIMIT = "900"
Write-Host "Running 12 tasks through real Qwen, budget $budget ..."
& $py run_agent.py --tasks-dir $tasks --strategy baseline 2>&1 | Tee-Object -FilePath (Join-Path $run "run.log")
& $py tools\evaluate.py $tasks (Join-Path $run "tasks_truth.json") 2>&1 | Tee-Object -FilePath (Join-Path $run "score.txt")
Remove-Item Env:\LLM_API_KEY -ErrorAction SilentlyContinue
Remove-Item Env:\HARNESS_DISABLE_DET, Env:\BUDGET, Env:\HARNESS_TRACE, Env:\HARNESS_TIME_LIMIT -ErrorAction SilentlyContinue
Write-Host ""
Write-Host "Results: $run"
Read-Host "Done. Press Enter to close"
