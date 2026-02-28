FROM python:3.11-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
EXPOSE 8000

# Hosted runtime entrypoint reads PORT from env and starts Uvicorn.
CMD ["python", "scripts/start_server.py"]
