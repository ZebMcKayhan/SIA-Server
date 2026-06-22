FROM python:3.12-slim

# Prevent Python stdout/stderr buffering
ENV PYTHONUNBUFFERED=1

# Application directory
WORKDIR /opt/sia-server

# Install CA certificates for HTTPS/SSL
RUN apt-get update && apt-get install -y \
    ca-certificates \
 && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copy application files
COPY *.py ./
COPY galaxy/*.py ./galaxy/
COPY providers/*.py ./providers/

# Optional config mount location
VOLUME ["/config"]

# Start server
CMD ["python3", "-u", "sia-server.py", "--config", "/config/sia-server.conf"]
