FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /code
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app
COPY migrations ./migrations
COPY alembic.ini .
COPY scripts/start.py ./scripts/start.py
RUN useradd --create-home appuser && mkdir /data && chown appuser:appuser /data
USER appuser
EXPOSE 8000
CMD ["python", "scripts/start.py"]
