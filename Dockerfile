FROM python:3.9-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Install poetry
RUN pip install --no-cache-dir poetry

# Copy dependency files
COPY pyproject.toml poetry.lock* ./

# Install dependencies (without installing the project itself)
RUN poetry config virtualenvs.create false \
    && poetry install --only main --no-interaction --no-ansi --no-root

# Copy application files
COPY handelsregister.py .
COPY api.py .

# Expose port
EXPOSE 5000

# Run the API server
CMD ["python", "api.py", "--host", "0.0.0.0", "--port", "5000"]
