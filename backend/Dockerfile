FROM python:3.12-slim

WORKDIR /srv/ivl
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app

# Audit log is mandatory: /verify answers 503 if this file cannot be written.
ENV IVL_TELEMETRY_PATH=/var/log/ivl/telemetry.jsonl
RUN mkdir -p /var/log/ivl
EXPOSE 8000
HEALTHCHECK CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health').status==200 else 1)"
CMD ["uvicorn", "app.api:app", "--host", "0.0.0.0", "--port", "8000"]
