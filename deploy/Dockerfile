FROM python:3.12-slim

WORKDIR /app

# Dependencies first so code changes do not rebuild the whole layer.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY classify.py service.py store.py ./
COPY static/ ./static/

# Written to a mounted volume so decisions survive container rebuilds.
ENV DB_PATH=/data/cod.db
RUN mkdir -p /data

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=4).status==200 else 1)"

CMD ["uvicorn", "service:app", "--host", "0.0.0.0", "--port", "8000"]
