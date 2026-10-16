# ModelArena user guide — 0.2.0

ModelArena is a small local benchmark studio: edit or import a labeled question set, compare two CPU extractive baselines, or call your own local OpenAI-compatible LLM. It reports actual measured latency, exact-match accuracy, completion counts, per-run failures and case-level predictions. Session comparisons retain the original input for each run.

## Workflow

1. Load synthetic cases or import a CSV with headers `question,context,expected_answer`. JSON may be a request object or an array of case objects.
2. Edit labels/context and choose **Two CPU extractive baselines** to test the whole workflow without a model server.
3. Set repeats, then choose **Run benchmark**. Inspect successful/attempted counts before comparing accuracy.
4. To test an LLM, configure a local server as described below, select **Local OpenAI-compatible LLM**, and enter the loaded model name.
5. Compare session rows from different runs. Export the benchmark setup or the full session results before refreshing the page.

Examples are explicitly synthetic. Imports and edits mark provenance unverified. Results for the current setup clear when it changes; previous session comparisons are labeled historical runs and retain their original inputs. A response to a request whose inputs changed during execution is discarded.

## Local LLM setup

Use an already installed OpenAI-compatible local CPU server, such as Ollama or llama.cpp, with model weights you have permission to use. No model is automatically installed or downloaded by ModelArena. Configure the operator-only environment variable before launching the app:

```sh
MODELARENA_LLM_URL=http://127.0.0.1:11434/v1/chat/completions uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Docker Desktop compose defaults to the fixed `host.docker.internal` bridge. If your model server uses a different local port, set `MODELARENA_LLM_URL` before `docker compose up`. Accepted addresses are numeric loopback IPs or exactly `host.docker.internal`; arbitrary request-provided provider URLs are not supported. Proxies and redirects are disabled. This does not configure the model server itself; check its local access settings. No paid-provider credentials are accepted by the app.

## Methods and output

`first_sentence` returns the first context sentence. `lexical_retrieval` returns the sentence with greatest non-stopword overlap with the question, breaking ties by first occurrence. These are **extractive baselines, not LLM inference**.

`local_llm` sends a user message containing the context/question, temperature 0 and your requested output limit. Each repetition is actually invoked. Latency measures adapter execution including local HTTP overhead for local_llm, and excludes dataset construction/loading. p95 uses nearest rank. Accuracy is normalized exact match over successful runs only, across repetitions. Reported case prediction is the last successful prediction for that case, not every repetition. Failures show case/repeat/type; a failed run has no invented prediction or latency. All-failure runs have null accuracy/latency.

An answer can be factually correct yet score zero because exact match penalizes phrasing or extra words. No semantic judge or ranking-by-statistical-significance is provided. A single short synthetic question is not a model quality benchmark.

## Bounds and troubleshooting

1–50 cases, 1–10 repeats, timeout 0–120 seconds (positive), output limit 1–2048 tokens, response cap 1 MiB. HTTP request body limit 2 MiB. Cases require nonblank question/context/expected answer. Model requests are sequential. HTTP timeouts apply to individual network phases and do not promise a total elapsed deadline, so large runs may take minutes.

- Failed local runs: confirm the model server is listening, the operator URL is valid, and the model name exists. A generic error avoids exposing sensitive endpoint details.
- Docker cannot reach the host server: check MODELARENA_LLM_URL and the model server's host access settings. Docker's own `127.0.0.1` refers to the app container.
- Null latency/accuracy: every request failed. This is not a quality result.
- Session disappears: comparisons are browser-memory only. Export before reloading.
- Old 0.1.0 evidence includes a successful actual CPU LLM run, but those historical measurements do not certify a new model or this rebuilt UI. Fresh validation belongs in `evidence/rebuild/`.

## Run locally

Docker (recommended):

```sh
docker compose up --build
```

Open http://localhost:8000. The interface, API reference at `/docs`, and user guide at `/guide` are served by the same app. The host port binds to localhost. Change only the host side of `8000:8000` if another app uses that port. The container runs as a non-root user with a read-only filesystem.

Python 3.12 or later:

```sh
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements-dev.txt
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

## Tests and release gates

```sh
python -m pytest -q
node --test tools/test_ui.mjs
python -m bandit -q -r app
python -m pip_audit -r requirements.txt
```

Node 22 is used for browser-independent CSV/export logic tests; it is not needed to serve the application. Python tests include actual core calculations, validation failures and in-process HTTP integration. They do not establish Docker deployment or browser interaction success. Rebuild evidence belongs in `evidence/rebuild/`; earlier evidence is historical and does not validate this version. CI includes locked dependency installation, test/security gates, image scanning and secret scanning. Branch protection and release publication remain separate operator actions; no publication success is claimed by this README.

MIT licensed. No paid service or new model download is required. Data is processed by this app server when you run an analysis. Inputs/results are not automatically saved by this application. JSON exports may contain the original input and sensitive values; inspect them before sharing. There is no authentication or rate limiter. Keep the localhost binding or supply access controls before exposing the server.
