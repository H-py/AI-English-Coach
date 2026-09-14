# Backend image for AI Reading Coach.
FROM python:3.11-slim

# Set environment variables for Python best practices.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Install system dependencies required by asyncpg.
RUN apt-get update \
    && apt-get install -y --no-install-recommends gcc libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies first to leverage Docker layer caching.
# 国内服务器构建时可传入镜像加速：--build-arg PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple
COPY requirements.txt .
ARG PIP_INDEX_URL=https://pypi.org/simple
RUN pip install -r requirements.txt -i ${PIP_INDEX_URL}

# Copy the application source code.
COPY . .

EXPOSE 8000

# Run the app with uvicorn. In development the --reload flag is added by the
# compose override or when running locally outside the container.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
