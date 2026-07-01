FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONIOENCODING=utf-8

WORKDIR /workspace

# OS deps for HTTP fetching and basic tooling
RUN apt-get update && apt-get install -y --no-install-recommends \
        git \
        curl \
        unzip \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Python deps first for layer caching
COPY requirements.txt /tmp/requirements.txt
RUN pip install --upgrade pip && pip install -r /tmp/requirements.txt

# Copy source + competition CSVs. data/, outputs/, artifacts/ are mounted as volumes
# at runtime (see docker-compose.yml) so they survive container restarts.
COPY src ./src
COPY skills ./skills
COPY references ./references
COPY train.csv test.csv submission_example.csv ./

# Default: drop into a shell so the user can run any pipeline step.
CMD ["bash"]
