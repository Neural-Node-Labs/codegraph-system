FROM python:3.11-slim

WORKDIR /code

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY entrypoint.sh .
RUN chmod +x entrypoint.sh

ENV CODEGRAPH_DB=/data/graph.db
ENV PROJECTS_ROOT=/data/projects
ENV PYTHONPATH=/code

VOLUME ["/data"]
EXPOSE 8000

ENTRYPOINT ["./entrypoint.sh"]
