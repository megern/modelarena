import re
import time
import statistics
import os
import ipaddress
from urllib.parse import urlparse
from typing import Literal
import httpx
from pydantic import BaseModel, ConfigDict, Field


class Case(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    question: str = Field(min_length=1, max_length=10000)
    context: str = Field(min_length=1, max_length=30000)
    expected_answer: str = Field(min_length=1, max_length=10000)


class BenchmarkRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    cases: list[Case] = Field(min_length=1, max_length=50)
    repeats: int = Field(default=3, ge=1, le=10)
    adapter: Literal["baselines", "local_llm"] = "baselines"
    model: str = Field(default="local-model", min_length=1, max_length=200)
    timeout_seconds: float = Field(default=30, gt=0, le=120)
    max_tokens: int = Field(default=128, ge=1, le=2048)


STOP = {
    "the",
    "a",
    "an",
    "is",
    "are",
    "was",
    "were",
    "what",
    "which",
    "who",
    "how",
    "many",
    "of",
    "in",
    "to",
    "does",
    "do",
    "and",
    "for",
}


def words(s):
    return re.findall(r"\w+", s.casefold())


def predict(case, method):
    sentences = [
        s.strip() for s in re.split(r"(?<=[.!?])\s+", case.context) if s.strip()
    ]
    if method == "first_sentence":
        return sentences[0]
    q = set(words(case.question)) - STOP
    return max(sentences, key=lambda s: len(q & (set(words(s)) - STOP)))


def local_completion(case, req):
    url = os.getenv("MODELARENA_LLM_URL", "http://127.0.0.1:8080/v1/chat/completions")
    parsed = urlparse(url)
    try:
        loopback = ipaddress.ip_address(parsed.hostname or "").is_loopback
    except ValueError:
        loopback = parsed.hostname == "host.docker.internal"
    if (
        parsed.scheme not in {"http", "https"}
        or not loopback
        or parsed.username
        or parsed.password
    ):
        raise ValueError(
            "MODELARENA_LLM_URL must point to a numeric loopback IP or host.docker.internal"
        )
    payload = {
        "model": req.model,
        "messages": [
            {
                "role": "user",
                "content": "Answer using only this context.\nContext: "
                + case.context
                + "\nQuestion: "
                + case.question,
            }
        ],
        "max_tokens": req.max_tokens,
        "temperature": 0,
    }
    # Disable environment proxies; never redirect local inference to other hosts.
    with httpx.Client(
        timeout=req.timeout_seconds, trust_env=False, follow_redirects=False
    ) as client:
        with client.stream("POST", url, json=payload) as response:
            response.raise_for_status()
            chunks = []
            size = 0
            for chunk in response.iter_bytes():
                size += len(chunk)
                if size > 1048576:
                    raise ValueError("model response exceeds 1 MiB")
                chunks.append(chunk)
    import json

    data = json.loads(b"".join(chunks))
    content = data["choices"][0]["message"]["content"]
    if not isinstance(content, str):
        raise ValueError("model response content must be text")
    return content


def analyze(req: BenchmarkRequest):
    results = []
    methods = (
        ["first_sentence", "lexical_retrieval"]
        if req.adapter == "baselines"
        else ["local_llm"]
    )
    for method in methods:
        times = []
        predictions = []
        scores = []
        errors = []
        for index, case in enumerate(req.cases):
            pred = None
            for repeat in range(req.repeats):
                start = time.perf_counter_ns()
                try:
                    pred = (
                        local_completion(case, req)
                        if method == "local_llm"
                        else predict(case, method)
                    )
                    scores.append(float(words(case.expected_answer) == words(pred)))
                    times.append((time.perf_counter_ns() - start) / 1e6)
                except (
                    httpx.HTTPError,
                    ValueError,
                    KeyError,
                    IndexError,
                    TypeError,
                ) as exc:
                    errors.append(
                        {
                            "case_index": index,
                            "repeat": repeat,
                            "error_type": type(exc).__name__,
                            "message": "Local model request failed; verify operator configuration and server response.",
                        }
                    )
            predictions.append(pred)
        ordered = sorted(times)
        results.append(
            {
                "adapter": method,
                "mean_latency_ms": statistics.mean(times) if times else None,
                "p95_latency_ms": ordered[
                    max(0, __import__("math").ceil(0.95 * len(ordered)) - 1)
                ]
                if ordered
                else None,
                "exact_match_accuracy": statistics.mean(scores) if scores else None,
                "predictions": predictions,
                "successful_runs": len(times),
                "measured_runs": len(times),
                "attempted_runs": len(req.cases) * req.repeats,
                "errors": errors,
            }
        )
    return {
        "results": results,
        "dataset_size": len(req.cases),
        "limitations": [
            "Built-in baselines are extractive CPU methods, not LLMs. local_llm calls an operator-supplied local OpenAI-compatible server via numeric loopback or the fixed Docker host bridge.",
            "Timings include adapter execution and local HTTP round trips for local_llm, and vary by machine.",
            "Exact match ignores case and punctuation. Accuracy covers successful runs only; check errors and successful_runs.",
            "Synthetic labels and transport tests do not establish real model quality. No model weights are bundled.",
        ],
    }
