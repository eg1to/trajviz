# API do trajviz (FastAPI). Contexto de build: backend/
FROM python:3.12-slim
ENV UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never PYTHONUNBUFFERED=1
RUN pip install --no-cache-dir uv==0.13.8
# Estrutura espelha o repositório: main.py usa parents[2] como raiz (data/samples, results)
WORKDIR /app/backend
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY app ./app
RUN mkdir -p /app/data/samples /app/results/gold /app/backend/.cache
EXPOSE 8000
CMD [".venv/bin/uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
