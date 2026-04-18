FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Expose the requested port
EXPOSE 8002

# Run gunicorn on port 8002
CMD ["gunicorn", "--bind", "0.0.0.0:8002", "app:app"]
