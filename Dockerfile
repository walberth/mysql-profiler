# Use official Python image
FROM python:3.12-slim-bookworm

# Set working directory
WORKDIR /app

# Copy requirement files and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY *.py ./
COPY templates ./templates
COPY static ./static
COPY icon-rbg.png ./static/icon-rbg.png

# Run the script
CMD ["python", "mysql-profiler.py"]
