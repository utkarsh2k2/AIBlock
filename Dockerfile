FROM python:3.11-slim

WORKDIR /app

RUN pip install --no-cache-dir fastapi "uvicorn[standard]" httpx

COPY src/ src/
COPY minimal_server.py .

# Ensure static assets exist so /home, /mark3, etc. work
RUN test -f src/aiblock/static/mark3.html && test -f src/aiblock/static/ai-or-not.html || (echo "Missing static files" && exit 1)

EXPOSE 8000

ENV PORT=8000
ENV PYTHONPATH=/app
CMD ["/bin/sh", "-c", "uvicorn minimal_server:app --host 0.0.0.0 --port ${PORT}"]
