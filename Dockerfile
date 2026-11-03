FROM python:3.12-slim
WORKDIR /app

# Réglages identiques dans tous les conteneurs
ENV PYTHONUNBUFFERED=1
ENV STREAMLIT_SERVER_HEADLESS=true

# 1. Les dépendances (pyirsdk, streamlit… versions figées)
COPY requirements.txt .
RUN pip install -r requirements.txt

# 2. RaceBoard lui-même
COPY pyproject.toml .
COPY src/ src/
RUN pip install .

# 3. Au démarrage : le dashboard, qui écoute sur le port 8501
EXPOSE 8501
CMD ["python", "-m", "raceboard.dashboard"]
