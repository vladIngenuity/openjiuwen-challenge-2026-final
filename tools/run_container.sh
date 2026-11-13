#!/usr/bin/env bash
set -euo pipefail

# Usage: TASKS_DIR=/absolute/tasks CPUSET=0,1,2,3,4,5,6,7 bash tools/run_container.sh
image=${IMAGE:-hack:latest}
tasks_dir=${TASKS_DIR:?Set TASKS_DIR to an absolute directory containing task subdirectories}
cpu_set=${CPUSET:?Set CPUSET to exactly eight distinct logical CPU IDs, comma-separated}
network=${CONTAINER_NETWORK:-hack-net}
strategy=${HARNESS_STRATEGY:-empirical_hybrid}

if [[ $tasks_dir != /* || ! -d $tasks_dir ]]; then
  echo 'TASKS_DIR must be an existing absolute directory' >&2
  exit 2
fi
if [[ ! $cpu_set =~ ^(0|[1-9][0-9]*)(,(0|[1-9][0-9]*)){7}$ ]]; then
  echo 'CPUSET must contain exactly eight comma-separated CPU IDs' >&2
  exit 2
fi
IFS=, read -r -a cpu_ids <<< "$cpu_set"
declare -A seen=()
for cpu_id in "${cpu_ids[@]}"; do
  if [[ -v seen[$cpu_id] ]]; then
    echo 'CPUSET contains duplicate CPU IDs' >&2
    exit 2
  fi
  seen[$cpu_id]=1
done
if [[ -z ${LLM_BASE_URL:-} || -z ${LLM_API_KEY:-} ]]; then
  echo 'Set LLM_BASE_URL and LLM_API_KEY in the environment' >&2
  exit 2
fi
if ! command -v docker >/dev/null 2>&1; then
  echo 'Docker CLI is required to run the image' >&2
  exit 127
fi

exec docker run --rm --init --platform linux/amd64 \
  --network "$network" --cpuset-cpus "$cpu_set" --cpus=8 --memory=16g \
  --user "$(id -u):$(id -g)" --read-only --tmpfs /tmp:rw,nosuid,nodev,size=2g \
  --cap-drop ALL --pids-limit 512 --security-opt no-new-privileges \
  --mount "type=bind,src=$tasks_dir,dst=/data/tasks" \
  -e LLM_BASE_URL -e LLM_API_KEY -e BUDGET -e HARNESS_TIME_LIMIT \
  -e LLM_CONCURRENCY -e HARNESS_WORKERS -e HARNESS_REASONING_USAGE \
  -e HARNESS_ISOLATION -e HARNESS_STRATEGY \
  "$image" --tasks-dir /data/tasks --strategy "$strategy" "$@"
