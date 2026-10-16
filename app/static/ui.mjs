import {
  $,
  el,
  clear,
  metric,
  table,
  analyze,
  status,
  readFile,
  resultDetails,
  limitations,
  setupDownloads,
  percent,
  number,
  parseCSV
} from "./common.mjs";
let revision = 0;
let latest = null,
  source = "manual input";
const session = [];
function cases() {
  return [...document.querySelectorAll(".case-row")].map((r) =>
    Object.fromEntries(
      ["question", "context", "expected_answer"].map((k) => [
        k,
        r.querySelector("." + k).value
      ])
    )
  );
}
function input() {
  return {
    cases: cases(),
    adapter: $("adapter").value,
    model: $("model").value,
    repeats: Number($("repeats").value),
    max_tokens: Number($("max-tokens").value),
    timeout_seconds: Number($("timeout").value)
  };
}
function invalidate() {
  revision++;
  latest = null;
  clear($("results"));
  $("results").append(
    el(
      "p",
      "Setup changed. Run a benchmark for these settings. Previous session comparisons retain their original inputs."
    )
  );
}
function drawCases(list) {
  clear($("cases"));
  list.forEach((c, i) => {
    const row = el("div", undefined, "editor-row case-row");
    row.append(el("h3", "Case " + (i + 1)));
    for (const [key, title] of [
      ["question", "Question"],
      ["context", "Context"],
      ["expected_answer", "Expected answer"]
    ]) {
      const label = el("label", title),
        field = el(key === "context" ? "textarea" : "input");
      field.className = key;
      field.value = c[key] || "";
      field.oninput = () => {
        invalidate();
        source = "user-edited input; provenance unverified";
      };
      label.append(field);
      row.append(label);
    }
    const remove = el("button", "Remove case");
    remove.onclick = () => {
      const v = cases();
      v.splice(i, 1);
      drawCases(v);
      invalidate();
      source = "user-edited input; provenance unverified";
    };
    row.append(remove);
    $("cases").append(row);
  });
}
function load(v) {
  const list = Array.isArray(v) ? v : v.cases;
  if (!Array.isArray(list) || !list.length || list.length > 50)
    throw Error("Import requires 1–50 cases.");
  if (
    list.some(
      (c) =>
        !c ||
        ["question", "context", "expected_answer"].some(
          (k) => typeof c[k] !== "string" || !c[k].trim()
        )
    )
  )
    throw Error(
      "Each case needs nonempty question, context and expected_answer text."
    );
  drawCases(list);
  if (!Array.isArray(v)) {
    for (const [key, id] of [
      ["adapter", "adapter"],
      ["model", "model"],
      ["repeats", "repeats"],
      ["max_tokens", "max-tokens"],
      ["timeout_seconds", "timeout"]
    ])
      if (v[key] !== undefined) $(id).value = v[key];
  }
  invalidate();
}
function drawSession() {
  clear($("session"));
  if (!session.length) {
    $("session").append(el("p", "No comparisons in this browser session."));
    return;
  }
  table(
    $("session"),
    [
      "Run / model",
      "Adapter",
      "Successful / attempted",
      "Exact match",
      "Mean ms"
    ],
    session.flatMap((run, i) =>
      run.result.results.map((r) => [
        `${i + 1}: ${run.input.adapter === "local_llm" ? run.input.model : "CPU baselines"}`,
        r.adapter,
        r.successful_runs + "/" + r.attempted_runs,
        percent(r.exact_match_accuracy),
        number(r.mean_latency_ms)
      ])
    )
  );
}
function render(r, request) {
  const root = $("results");
  clear(root);
  root.classList.remove("empty");
  for (const result of r.results) {
    const section = el("section");
    section.append(el("h3", result.adapter));
    const m = el("div", undefined, "metrics");
    metric(
      m,
      "Successful runs",
      result.successful_runs + "/" + result.attempted_runs
    );
    metric(
      m,
      "Exact-match accuracy",
      percent(result.exact_match_accuracy),
      "Successful runs only"
    );
    metric(m, "Mean latency", number(result.mean_latency_ms) + " ms");
    metric(m, "p95 latency", number(result.p95_latency_ms) + " ms");
    section.append(m);
    if (result.errors.length) {
      section.append(
        el(
          "p",
          result.errors.length +
            " run(s) failed. Do not compare accuracy without checking the failure rate.",
          "error"
        )
      );
      table(
        section,
        ["Case", "Repeat", "Failure", "Action"],
        result.errors.map((e) => [
          e.case_index + 1,
          e.repeat + 1,
          e.error_type,
          e.message
        ])
      );
    }
    table(
      section,
      ["Case", "Question", "Expected answer", "Last successful prediction"],
      request.cases.map((c, i) => [
        i + 1,
        c.question,
        c.expected_answer,
        result.predictions[i] ?? "No successful prediction"
      ])
    );
    root.append(section);
  }
  limitations(root, r.limitations);
  resultDetails(root, r);
}
$("add-case").onclick = () => {
  const v = cases();
  if (v.length >= 50) {
    status("Case limit is 50.", true);
    return;
  }
  v.push({ question: "", context: "", expected_answer: "" });
  drawCases(v);
  invalidate();
  source = "user-edited input; provenance unverified";
};
for (const id of ["adapter", "model", "repeats", "max-tokens", "timeout"])
  $(id).oninput = () => {
    invalidate();
    source = "user-edited input; provenance unverified";
  };
$("sample").onclick = () => {
  load({
    cases: [
      {
        question: "What color is the boat?",
        context: "The bicycle is green. The boat is blue.",
        expected_answer: "The boat is blue."
      },
      {
        question: "How many people are on the team?",
        context: "The synthetic team contains five people.",
        expected_answer: "The synthetic team contains five people."
      }
    ],
    adapter: "baselines",
    repeats: 3,
    max_tokens: 128,
    timeout_seconds: 30,
    model: "local-model"
  });
  source = "synthetic example";
  status(
    "Two synthetic benchmark cases loaded. Baselines require no model server."
  );
};
$("import").onchange = async (e) => {
  invalidate();
  const importRevision = revision;
  try {
    const f = e.target.files[0],
      text = await readFile(f);
    if (revision !== importRevision) return;
    load(
      f.name.toLowerCase().endsWith(".csv") ? parseCSV(text) : JSON.parse(text)
    );
    source = "imported user data; provenance unverified";
    status("Cases imported. Confirm labels before benchmarking.");
  } catch (err) {
    if (revision === importRevision) status(err.message, true);
  }
};
$("run").onclick = async () => {
  invalidate();
  const requestRevision = revision;
  $("run").disabled = true;
  try {
    const request = input();
    if (!request.cases.length) throw Error("Add at least one benchmark case.");
    const attempts = request.cases.length * request.repeats;
    status(
      request.adapter === "local_llm"
        ? `Running ${attempts} sequential local model requests. Per-request timeout ${request.timeout_seconds}s; connection and read timeouts are per I/O phase, not a total run deadline.`
        : "Measuring actual CPU baseline execution…"
    );
    const result = await analyze(request);
    if (revision !== requestRevision)
      throw Error(
        "Inputs changed during the request. Discarded its result; run again for the current setup."
      );
    latest = {
      input: request,
      source,
      result,
      finished_at: new Date().toISOString()
    };
    session.push(latest);
    render(result, request);
    drawSession();
    const errors = result.results.reduce((n, r) => n + r.errors.length, 0);
    status(
      errors
        ? "Benchmark finished with " +
            errors +
            " failed run(s). Inspect errors below."
        : "Benchmark finished. Measured results added to session comparisons.",
      errors > 0
    );
  } catch (e) {
    status(e.message, true);
  } finally {
    $("run").disabled = false;
  }
};
$("clear-session").onclick = () => {
  session.length = 0;
  invalidate();
  drawSession();
  status("Session comparisons cleared.");
};
setupDownloads(
  input,
  () => (session.length ? { runs: session } : null),
  "modelarena"
);
drawCases([{ question: "", context: "", expected_answer: "" }]);
