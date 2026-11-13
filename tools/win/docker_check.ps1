# Docker check (issue #5 / #11): build the image and run it the way the
# organizers might - no root, no capabilities, no network - on the 8 sample tasks.
# Optional second run goes through the real proxy (asks for the key, hidden).
# Results: runs\docker_<time>\ (tasks with answers, build.log, run.log).
$ErrorActionPreference = "Continue"
$root = Resolve-Path (Join-Path $PSScriptRoot "..\..")
Set-Location $root
& docker version --format "Docker {{.Server.Version}}" 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "Docker is not running. Start Docker Desktop, wait until it says 'Engine running', rerun."
    Read-Host "Press Enter"; exit 1
}
$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$run = Join-Path $root "runs\docker_$stamp"
New-Item -ItemType Directory -Force $run | Out-Null

Write-Host "== 1/3 build (first time: several minutes) =="
& docker build -t hack:latest . 2>&1 | Tee-Object -FilePath (Join-Path $run "build.log")
if ($LASTEXITCODE -ne 0) { Write-Host "BUILD FAILED - see $run\build.log"; Read-Host "Press Enter"; exit 1 }
& docker image ls hack:latest --format "image size: {{.Size}}" | Tee-Object -FilePath (Join-Path $run "build.log") -Append

Write-Host "== 2/3 offline run: user 1000, cap-drop ALL, no network =="
$tasks = Join-Path $run "tasks"
Copy-Item -Recurse samples $tasks
& docker run --rm --network none --cap-drop=ALL --security-opt no-new-privileges `
    --user 1000:1000 -v "${tasks}:/data/tasks" hack:latest --tasks-dir /data/tasks 2>&1 |
    Tee-Object -FilePath (Join-Path $run "run.log")
$n = (Get-ChildItem -Directory $tasks | Where-Object { Test-Path (Join-Path $_.FullName "answer.txt") } | Measure-Object).Count
"exit code: $LASTEXITCODE; tasks with answer.txt: $n of 8" |
    Tee-Object -FilePath (Join-Path $run "run.log") -Append

Write-Host ""
$ans = Read-Host "== 3/3 run in the container through the REAL proxy? 12 tasks, budget 6000 (y/N)"
if ($ans -eq "y") {
    $u = Read-Host "LLM_BASE_URL (Enter = https://api.neuraldeep.ru/v1)"
    if (-not $u) { $u = "https://api.neuraldeep.ru/v1" }
    $s = Read-Host "LLM_API_KEY (input hidden)" -AsSecureString
    $b = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($s)
    $env:LLM_API_KEY = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($b)
    [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($b)
    $env:LLM_BASE_URL = $u
    $live = Join-Path $run "live"
    New-Item -ItemType Directory -Force $live | Out-Null
    # generate tasks inside the image, so no local Python is needed
    & docker run --rm --user 1000:1000 -v "${live}:/out" --entrypoint python hack:latest `
        /app/tools/task_factory.py /out/tasks --n 12 --seed 7 --infeasible 0.2
    # the key is passed by name only (-e LLM_API_KEY): it never appears on a command line
    & docker run --rm --cap-drop=ALL --security-opt no-new-privileges --user 1000:1000 `
        -e LLM_BASE_URL -e LLM_API_KEY -e BUDGET=6000 `
        -e "HARNESS_DISABLE_DET=math,search,data_analysis,coding" -e HARNESS_TIME_LIMIT=900 `
        -e HARNESS_TRACE=/data/trace.json -v "${live}:/data" hack:latest --tasks-dir /data/tasks 2>&1 |
        Tee-Object -FilePath (Join-Path $run "live_run.log")
    & docker run --rm --user 1000:1000 -v "${live}:/data" --entrypoint python hack:latest `
        /app/tools/evaluate.py /data/tasks /data/tasks_truth.json 2>&1 |
        Tee-Object -FilePath (Join-Path $run "live_score.txt")
    Remove-Item Env:\LLM_API_KEY -ErrorAction SilentlyContinue
}
Write-Host ""
Write-Host "Results: $run"
Read-Host "Done. Press Enter to close"
