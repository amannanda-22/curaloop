FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 PORT=8000
WORKDIR /app
COPY backend/requirements.txt backend/requirements.txt
RUN pip install -r backend/requirements.txt
COPY backend/ backend/
COPY run.py ./
COPY frontend/dist frontend/dist
RUN useradd -m app && chown -R app /app
USER app
EXPOSE 8000
CMD ["python", "run.py"]
