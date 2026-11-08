FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY youtube_ingestion youtube_ingestion
ENV YT_LIBRARY=/library
ENTRYPOINT ["python", "-m", "youtube_ingestion"]
