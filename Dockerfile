FROM node:22-alpine AS frontend
WORKDIR /ui
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ .
RUN npm run build

FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /opt/respira
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY respira/ respira/
COPY --from=frontend /ui/dist/ frontend/dist/
CMD ["python", "-m", "uvicorn", "respira.web:app", "--host", "0.0.0.0", "--port", "8512"]
