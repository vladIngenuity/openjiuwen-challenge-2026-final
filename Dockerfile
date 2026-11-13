# openJiuwen Challenge 2026 harness - team "Индийская техподдержка"
FROM python:3.12.8-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    HOME=/tmp \
    TMPDIR=/tmp \
    SSRF_PROTECT_ENABLED=false \
    TRANSFORMERS_OFFLINE=1 \
    HF_HUB_OFFLINE=1 \
    TOKENIZERS_PARALLELISM=false \
    OMP_NUM_THREADS=1 \
    OPENBLAS_NUM_THREADS=1 \
    MKL_NUM_THREADS=1 \
    NUMEXPR_NUM_THREADS=1 \
    HARNESS_ISOLATION=auto \
    HARNESS_STRATEGY=empirical_hybrid
# auto: Landlock + seccomp when a trusted preflight shows the kernel provides
# them, otherwise resource limits only (logged).  The library default stays
# "strict"; the image opts in because an unknown evaluation host without
# Landlock would otherwise run no model code at all.

WORKDIR /app

# openJiuwen pinned; its whole dependency closure pinned via constraints
# generated from openJiuwen's own uv.lock (tag v0.1.19).
COPY requirements.txt constraints.txt ./
RUN apt-get update \
 && apt-get install -y --no-install-recommends libseccomp2 \
 && rm -rf /var/lib/apt/lists/* \
 && pip install -r requirements.txt -c constraints.txt \
 && find /usr/local/lib/python3.12 -name "__pycache__" -prune -exec rm -rf {} + \
 && find /usr/local/lib/python3.12 -name "*.pyc" -delete

COPY harness ./harness
COPY tools/selfcheck.py tools/task_factory.py tools/evaluate.py ./tools/
COPY samples ./samples
COPY run_agent.py README.md ./
COPY docs/project ./docs/project

# Runtime filesystem and network isolation is checked in the running container.
RUN python tools/selfcheck.py --api-only && rm -rf /tmp/* && \
    find /app -name "__pycache__" -prune -exec rm -rf {} +

ENTRYPOINT ["python", "/app/run_agent.py"]
CMD ["--tasks-dir", "/data/tasks"]
