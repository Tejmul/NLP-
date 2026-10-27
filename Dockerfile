# ---- build: install dependencies into a virtualenv ----
FROM python:3.12-slim AS build
ENV PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
RUN python -m venv /opt/venv
ENV PATH=/opt/venv/bin:$PATH
COPY requirements.txt .
RUN pip install -r requirements.txt

# ---- train: produce the model artifacts inside the image build ----
FROM build AS train
WORKDIR /app
COPY bankq ./bankq
COPY configs ./configs
COPY data/raw ./data/raw
RUN python -m bankq.ml.train

# ---- runtime: small image, non-root user ----
FROM python:3.12-slim AS runtime
ENV PATH=/opt/venv/bin:$PATH PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
RUN useradd --create-home --uid 10001 app
WORKDIR /app
COPY --from=build /opt/venv /opt/venv
COPY --chown=app bankq ./bankq
COPY --chown=app configs ./configs
COPY --chown=app web ./web
COPY --chown=app data/raw ./data/raw
COPY --from=train --chown=app /app/models ./models
RUN mkdir -p /app/data && chown app /app/data
USER app
EXPOSE 8077
HEALTHCHECK --interval=30s --timeout=3s --start-period=20s \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8077/ready').status==200 else 1)"
CMD ["uvicorn", "bankq.api.app:app", "--host", "0.0.0.0", "--port", "8077", "--proxy-headers"]
