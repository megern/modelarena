# ModelArena

Version 0.2.0 · CPU local tool · MIT

ModelArena is a small local benchmark studio: edit or import a labeled question set, compare two CPU extractive baselines, or call your own local OpenAI-compatible LLM. It reports actual measured latency, exact-match accuracy, completion counts, per-run failures and case-level predictions. Session comparisons retain the original input for each run.

## Try the interface

1. Load synthetic cases or import a CSV with headers `question,context,expected_answer`. JSON may be a request object or an array of case objects.
2. Edit labels/context and choose **Two CPU extractive baselines** to test the whole workflow without a model server.
3. Set repeats, then choose **Run benchmark**. Inspect successful/attempted counts before comparing accuracy.
4. To test an LLM, configure a local server as described below, select **Local OpenAI-compatible LLM**, and enter the loaded model name.
5. Compare session rows from different runs. Export the benchmark setup or the full session results before refreshing the page.

Examples are explicitly synthetic. Imports and edits mark provenance unverified. Results for the current setup clear when it changes; previous session comparisons are labeled historical runs and retain their original inputs. A response to a request whose inputs changed during execution is discarded.

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

## Methods and operating details

Read [the complete user guide](docs/USER_GUIDE.md) for calculations, input schemas, limitations and troubleshooting. The same guide is served at `/guide`. The API and browser use the same tested computation path.

API example using explicitly synthetic data:

```sh
curl --fail-with-body http://localhost:8000/analyze -H 'Content-Type: application/json' --data-binary @examples/synthetic.json
```
