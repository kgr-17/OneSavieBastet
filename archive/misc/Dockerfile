FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /workspace

RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    ripgrep \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /tmp/requirements.txt
RUN pip install -r /tmp/requirements.txt

COPY . /workspace

RUN mkdir -p /workspace/outputs

CMD ["python", "src/baseline.py", "--train-csv", "train.csv", "--test-csv", "test.csv", "--sample-submission", "submission_example.csv", "--output", "outputs/submission.csv"]
