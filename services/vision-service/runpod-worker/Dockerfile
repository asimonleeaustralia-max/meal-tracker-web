# syntax=docker/dockerfile:1.7
# RunPod worker image — deploy to RunPod Serverless, not to Azure.
#
# Pick a CUDA base image that matches your chosen model's requirements.
# `runpod/base:0.6.2-cuda12.1.0` is a reasonable default.
FROM runpod/base:0.6.2-cuda12.1.0

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY handler.py .

# RunPod looks for a `handler` callable in the file you specify with CMD
CMD ["python", "-u", "handler.py"]
