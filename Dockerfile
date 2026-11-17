# One image for both the API and the UI; docker-compose.yml picks the command.
FROM python:3.13-slim

# No .pyc files in the image; print logs straight away instead of buffering them
ENV PYTHONDONTWRITEBYTECODE=1 \
  PYTHONUNBUFFERED=1

WORKDIR /app

# Dependencies first: this layer is cached until requirements.txt changes
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ app/
COPY ui/ ui/
COPY deploy/ deploy/

# Don't run as root. chroma_db/ is created here so the volume mounted on it belongs to this user.
RUN useradd --create-home loanlens && mkdir chroma_db && chown loanlens chroma_db
USER loanlens

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
