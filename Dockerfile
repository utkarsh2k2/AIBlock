FROM python:3.11-slim

WORKDIR /app

RUN pip install --no-cache-dir fastapi "uvicorn[standard]" httpx

COPY src/ src/
COPY minimal_server.py .

EXPOSE 8000

CMD ["uvicorn", "minimal_server:app", "--host", "0.0.0.0", "--port", "8000"]
