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
COPY requirements.txt .
RUN pip install -r requirements.txt

# Copy the application source code.
COPY . .

EXPOSE 8000

# Run the app with uvicorn. In development the --reload flag is added by the
# compose override or when running locally outside the container.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
