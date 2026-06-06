FROM python:3.11-slim

# Install system dependencies (ffmpeg is required for video editing)
RUN apt-get update && \
    apt-get install -y --no-install-recommends ffmpeg curl && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy requirements and install
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application code
COPY . .

# Expose port (Render will bind to $PORT env var, which defaults to 8080)
EXPOSE 8080

# Run uvicorn server, binding to all interfaces and the PORT env var
CMD uvicorn main:app --host 0.0.0.0 --port ${PORT:-8080}
