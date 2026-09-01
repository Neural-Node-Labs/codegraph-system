FROM python:3.11-slim
WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY server.py .

ENV CODEGRAPH_API_URL=http://localhost:8000
# CODEGRAPH_API_KEY must be supplied at `docker run` time.

ENTRYPOINT ["python3", "server.py"]
