# ModelArena

Version 0.4.0 · CPU local tool · MIT

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

Node 22 is used for browser-independent CSV/export logic tests; it is not needed to serve the application. Python tests include actual core calculations, validation failures and in-process HTTP integration. They do not establish Docker deployment or browser interaction success. Fresh 0.4.0 evidence belongs in `evidence/improvements-0.4/`. `evidence/rebuild/` records the earlier 0.2.0 rebuild; it does not validate this version. CI includes locked dependency installation, test/security gates, image scanning and secret scanning. Branch protection and release publication remain separate operator actions; no publication success is claimed by this README.

MIT licensed. No paid service or new model download is required. Data is processed by this app server when you run an analysis. Inputs/results are not automatically saved by this application. JSON exports may contain the original input and sensitive values; inspect them before sharing. Optional server access and per-process admission are described in [Operations](docs/OPERATIONS.md). Localhost remains the default; public multi-user hosting requires additional infrastructure.

## Methods and operating details

Read [the complete user guide](docs/USER_GUIDE.md) for calculations, input schemas, limitations and troubleshooting. The same guide is served at `/guide`. The API and browser use the same tested computation path.

API example using explicitly synthetic data:

```sh
curl --fail-with-body http://localhost:8000/analyze -H 'Content-Type: application/json' --data-binary @examples/synthetic.json
```

## Quality and completion diagnostics (0.4.0)

Benchmark results now include **token F1**, median/minimum/maximum successful-run latency, completion ratio, and per-case success/failure counts, scores, errors and latency summaries. The session comparison table keeps these metrics with each original run. Full JSON exports preserve the same API details.

Token F1 uses a multiset of the same case-folded `\w+` tokens used for exact match. It is `2 × overlapping token occurrences / (predicted token count + reference token count)`. Repeated tokens count, so prediction `cat cat` against reference `cat` scores 2/3. Case and punctuation are ignored. If either sequence has no tokens, F1 is zero unless **both** have no tokens, which scores one. A whitespace-only prediction against a normal reference therefore scores zero; punctuation-only reference and prediction can score one. References still must be nonblank text. Token F1 is lexical agreement, not semantic or factual correctness.

Existing `exact_match_accuracy` and new `token_f1` average **successful runs only**. New `all_attempt_exact_match_accuracy` and `all_attempt_token_f1` count each failed attempt as zero, and `completion_ratio` is successful / attempted. A model with one successful perfect answer and three failed attempts has success-only accuracy 1, all-attempt accuracy .25, and completion ratio .25. Per-case metrics expose the same denominators. When all requests fail, success-only scores and latencies are null, while all-attempt scores and completion ratio are zero. Failure messages remain sanitized and do not include raw model-server responses.

Timing now explicitly excludes score computation. Mean/median/min/max and nearest-rank p95 cover successful adapter calls only. Failed attempts do not receive invented latency or quality values. No remote host relaxation, new model download, paid service or model-quality claim is introduced.

## Ephemeral background jobs (0.4)

The background-job panel submits the current benchmark snapshot, shows real completed/successful/failed attempt counts, polls status, requests cancellation and exports the job snapshot. It does not pretend to run requests when polling fails. Changing the editor never relabels an old job as a run of the new inputs: completed old-snapshot results enter historical session comparisons and can be exported with their original input.

API: `POST /jobs` returns 202 for `{ "request": <ordinary benchmark request>, "budget_seconds": 120 }`; poll `GET /jobs/{job_id}`; `DELETE /jobs/{job_id}` returns 202 acknowledging a cancellation request. Unknown/expired jobs return 404. `examples/synthetic-job.json` runs real CPU extractive methods without a model server. Existing synchronous `/analyze` remains available and **is separate from the background worker's queue**; its calls do not join the queue or acquire the background execution budget.

Each app process has one background worker and at most two queued requests; a fourth admitted-outstanding job receives 429. This is process-local memory, not a durable/distributed scheduler. Queued cancellation prevents execution. Running cancellation sets a flag; status remains running until a cooperative checkpoint acknowledges it, or the job finishes first. The overall execution budget is 0.1–300seconds, starts when the worker begins (not during queue wait), and is checked between attempts and model response chunks. Per-request HTTP timeouts are reduced to remaining budget. **This is cooperative, not a hard wall-clock kill guarantee**: an in-flight connection/read phase may wait up to its timeout before the next checkpoint. HTTP timeout phases and OS scheduling can make observed elapsed time exceed the requested budget. Do not promise hard deadlines from this tool.

Job completion means the benchmark engine returned, not that every model request succeeded or passed quality checks. Successful/failed attempt denominators remain in the result. Cancellation, budget exhaustion or worker failure does not fabricate partial benchmark quality; progress counters remain available but full predictions may be absent. Error text is sanitized. Progress counts accepted completed/scored attempts; an interrupted in-flight attempt may remain uncounted.

Completed records expire after 300seconds and only the eight most recently completed records are retained, so eviction/restart can remove a record earlier. Completed requests are discarded from memory. Jobs cap accumulated generated-answer text at 512KiB across attempts and retained serialized results at 1 MiB; crossing a cap fails the job explicitly, rather than silently truncating a supposedly complete benchmark. Reduce cases/repeats/token limits if these bounds are exceeded. Existing local-host allowlist, proxy/redirect restrictions and 1 MiB-per-model-response cap remain unchanged. There is no new model download or paid/external-provider capability.
