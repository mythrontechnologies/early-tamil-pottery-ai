# Early Tamil Pottery AI - container image.
#
# CPU by default. For an NVIDIA GPU build with the CUDA wheels:
#   docker build --build-arg TORCH_INDEX=https://download.pytorch.org/whl/cu126 -t etpai:gpu .
# and run with `--gpus all` (needs the NVIDIA Container Toolkit on the host).
#
# DATA IS NOT IN THE IMAGE. data/ (images, records, annotation store) is mounted at run
# time (see docker-compose.yml): research images may not be redistributable, and the
# annotation store must persist outside the container. See docs/DEPLOYMENT.md.

ARG PYTHON_VERSION=3.13
FROM python:${PYTHON_VERSION}-slim

ARG TORCH_INDEX=https://download.pytorch.org/whl/cpu
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# OpenCV needs these shared libraries; git lets experiment records capture the commit.
RUN apt-get update \
 && apt-get install -y --no-install-recommends libgl1 libglib2.0-0 git \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt ./
RUN pip install torch torchvision --index-url "${TORCH_INDEX}" \
 && pip install -r requirements.txt

COPY . .
RUN useradd --create-home --uid 10001 appuser \
 && mkdir -p data/metadata outputs models \
 && chown -R appuser:appuser /app
USER appuser

EXPOSE 8501 8765
HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8501/_stcore/health', timeout=4)" || exit 1

CMD ["streamlit", "run", "app/main.py", "--server.address=0.0.0.0", "--server.port=8501", \
     "--server.headless=true", "--browser.gatherUsageStats=false"]
