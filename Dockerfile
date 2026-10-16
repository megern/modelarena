FROM python:3.12-alpine@sha256:1b668429b3511ab407d8e00648891631b0b1a4d7e15e3ca70f38ab5b91ad4ab4
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1
RUN timeout -k 10 120 apk add --no-cache zlib=1.3.2-r1
WORKDIR /service
COPY requirements.lock .
RUN pip install --no-cache-dir --require-hashes -r requirements.lock && python -m pip uninstall -y pip && rm -rf /usr/local/lib/python3.12/ensurepip && adduser -D -u 10001 runner
COPY app ./app
USER runner
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health',timeout=3)"
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--limit-concurrency", "16"]
