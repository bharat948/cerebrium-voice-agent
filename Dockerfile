FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /srv
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app
COPY web ./web
COPY migrations ./migrations
COPY alembic.ini ./alembic.ini
COPY scripts ./scripts
COPY scripts/container-entrypoint.py /srv/container-entrypoint.py
RUN mkdir -p /data && useradd --system --uid 10001 --create-home appuser && chown appuser:appuser /data
# The entrypoint fixes ownership of a newly mounted Render disk, then drops root
# privileges to appuser before starting Uvicorn. PORT is provided by Render.
EXPOSE 8000
CMD ["python", "/srv/container-entrypoint.py"]
