FROM python:3.12-alpine@sha256:92abd2ba1bdfb48b1e2ac224b582dd1558d0d4bb11c903b126b5bf9c448fd656
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1
WORKDIR /service
COPY requirements.lock .
RUN pip install --no-cache-dir --require-hashes -r requirements.lock && python -m pip uninstall -y pip && rm -rf /usr/local/lib/python3.12/ensurepip && adduser -D -u 10001 runner
COPY app ./app
USER runner
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s CMD ["/bin/busybox", "wget", "-q", "-T", "3", "-O", "/dev/null", "http://127.0.0.1:8000/health"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--limit-concurrency", "16"]
