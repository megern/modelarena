import test from "node:test";
import assert from "node:assert/strict";
import {
  parseCSV,
  inferValue,
  csvText,
  el,
  readFile,
  errorMessage
} from "../app/static/common.mjs";

test("CSV supports BOM, escaped quotes, embedded newlines, CRLF and empty cells", () => {
  const rows = parseCSV(
    '\uFEFFname,note,value\r\nAda,"says ""hello""\nand goodbye",\r\nBo,plain,2\r\n'
  );
  assert.deepEqual(rows, [
    { name: "Ada", note: 'says "hello"\nand goodbye', value: "" },
    { name: "Bo", note: "plain", value: "2" }
  ]);
});

test("CSV rejects ambiguity and reports the physical data-row position", () => {
  assert.throws(() => parseCSV("x,x\n1,2"), /unique/);
  assert.throws(() => parseCSV("x,y\n1"), /row 2 has 1 fields/);
  assert.throws(() => parseCSV('x\n"unclosed'), /unclosed/);
  assert.throws(() => parseCSV('x\n"quoted"tail'), /Unexpected text/);
  assert.throws(() => parseCSV('x\nnot"quoted'), /quote must start/);
});

test("Numeric inference preserves identifiers and rejects overflow", () => {
  assert.equal(inferValue("0012"), "0012");
  assert.equal(inferValue("1e3"), 1000);
  assert.equal(inferValue("-4.5"), -4.5);
  assert.equal(inferValue(""), null);
  assert.equal(inferValue("false"), false);
  assert.equal(inferValue("=SUM(A1:A2)"), "=SUM(A1:A2)");
  assert.throws(() => inferValue("1e400"), /Rescale/);
});

test("CSV export neutralizes formula cells including whitespace prefixes; negatives stay numeric", () => {
  const result = csvText([
    [
      "=2+2",
      "+command",
      "-command",
      "@SUM(A1:A2)",
      "\t=cmd",
      "\r\n+cmd",
      -2.5,
      'ordinary "quote"'
    ]
  ]);
  assert.equal(
    result,
    '"\'=2+2","\'+command","\'-command","\'@SUM(A1:A2)","\'\t=cmd","\'\r\n+cmd","-2.5","ordinary ""quote"""'
  );
});

test("Untrusted values are assigned to textContent, never interpreted as HTML", () => {
  const hostile = '<img src=x onerror="globalThis.compromised=true">';
  globalThis.document = {
    createElement: (tag) => ({ tag, textContent: "", className: "" })
  };
  const value = el("td", hostile);
  assert.equal(value.textContent, hostile);
  assert.equal(value.innerHTML, undefined);
  delete globalThis.document;
});

test("File size check happens before reading and API validation paths are actionable", async () => {
  let read = false;
  await assert.rejects(
    () =>
      readFile({
        size: 2097153,
        text: () => {
          read = true;
          return Promise.resolve("x");
        }
      }),
    /2 MiB/
  );
  assert.equal(read, false);
  assert.equal(
    errorMessage({
      detail: [{ loc: ["body", "rows", 2, "x"], msg: "invalid number" }]
    }),
    "rows.2.x: invalid number"
  );
});

// These tests import the production UI module, invoke its file handler, and delay File.text().
// A DOM adapter supplies browser primitives only; the import/generation logic is not copied.
test("Delayed actual UI file import cannot replace a newer synthetic sample", async () => {
  const { readFile: readLocal } = await import("node:fs/promises");
  const { documentFromHTML, deferred } = await import("./ui-test-dom.mjs");
  globalThis.document = documentFromHTML(
    await readLocal(new URL("../app/index.html", import.meta.url), "utf8")
  );
  await import("../app/static/ui.mjs?test=late-success");
  const read = deferred();
  const pending = document.getElementById("import").onchange({
    target: {
      files: [{ name: "setup.json", size: 100, text: () => read.promise }]
    }
  });
  document.getElementById("sample").onclick();
  const values = document.snapshot();
  const message = document.getElementById("status").textContent;
  read.resolve(
    await readLocal(
      new URL("../examples/synthetic.json", import.meta.url),
      "utf8"
    )
  );
  await pending;
  assert.deepEqual(document.snapshot(), values);
  assert.equal(document.getElementById("status").textContent, message);
  delete globalThis.document;
});

test("Late actual UI file rejection cannot replace newer status", async () => {
  const { readFile: readLocal } = await import("node:fs/promises");
  const { documentFromHTML, deferred } = await import("./ui-test-dom.mjs");
  globalThis.document = documentFromHTML(
    await readLocal(new URL("../app/index.html", import.meta.url), "utf8")
  );
  await import("../app/static/ui.mjs?test=late-rejection");
  const read = deferred();
  const pending = document.getElementById("import").onchange({
    target: {
      files: [{ name: "setup.json", size: 100, text: () => read.promise }]
    }
  });
  document.getElementById("sample").onclick();
  const message = document.getElementById("status").textContent;
  read.reject(Error("Old file read failed"));
  await pending;
  assert.equal(document.getElementById("status").textContent, message);
  delete globalThis.document;
});

test("Actual UI accepts an unsuperseded JSON file import", async () => {
  const { readFile: readLocal } = await import("node:fs/promises");
  const { documentFromHTML } = await import("./ui-test-dom.mjs");
  globalThis.document = documentFromHTML(
    await readLocal(new URL("../app/index.html", import.meta.url), "utf8")
  );
  await import("../app/static/ui.mjs?test=current-import");
  const text = await readLocal(
    new URL("../examples/synthetic.json", import.meta.url),
    "utf8"
  );
  await document.getElementById("import").onchange({
    target: {
      files: [{ name: "setup.json", size: text.length, text: async () => text }]
    }
  });
  assert.match(document.getElementById("status").textContent, /imported/i);
  delete globalThis.document;
});

test("Delayed actual UI file import cannot replace a manual field edit", async () => {
  const { readFile: readLocal } = await import("node:fs/promises");
  const { documentFromHTML, deferred } = await import("./ui-test-dom.mjs");
  globalThis.document = documentFromHTML(
    await readLocal(new URL("../app/index.html", import.meta.url), "utf8")
  );
  await import("../app/static/ui.mjs?test=manual-edit");
  document.getElementById("sample").onclick();
  const read = deferred();
  const pending = document.getElementById("import").onchange({
    target: {
      files: [{ name: "setup.json", size: 100, text: () => read.promise }]
    }
  });
  const field = document.getElementById("model");
  field.value = "User changed this input while the file was reading";
  field.dispatch("input");
  const values = document.snapshot();
  read.resolve(
    await readLocal(
      new URL("../examples/synthetic.json", import.meta.url),
      "utf8"
    )
  );
  await pending;
  assert.deepEqual(document.snapshot(), values);
  delete globalThis.document;
});

test("CSV preserves explicit all-empty records at the beginning and end", () => {
  assert.deepEqual(parseCSV("x,y\n,\n1,2"), [
    { x: "", y: "" },
    { x: "1", y: "2" }
  ]);
  assert.deepEqual(parseCSV("x,y\n1,2\n,"), [
    { x: "1", y: "2" },
    { x: "", y: "" }
  ]);
  const inferred = parseCSV("x,y\n,\n1,2").map((row) =>
    Object.fromEntries(Object.entries(row).map(([k, v]) => [k, inferValue(v)]))
  );
  assert.deepEqual(inferred, [
    { x: null, y: null },
    { x: 1, y: 2 }
  ]);
  assert.equal(inferred.length, 2);
  assert.equal(inferred.filter((row) => row.x === null).length, 1);
  assert.equal(inferred.filter((row) => row.y === null).length, 1);
});

test("CSV preserves quoted empty single/multiple fields and multiline values", () => {
  assert.deepEqual(parseCSV('a\n""\n1'), [{ a: "" }, { a: "1" }]);
  assert.deepEqual(parseCSV('x,y\n"",""\n1,2'), [
    { x: "", y: "" },
    { x: "1", y: "2" }
  ]);
  assert.deepEqual(parseCSV('x,y\n"\n",""\n1,2'), [
    { x: "\n", y: "" },
    { x: "1", y: "2" }
  ]);
  assert.deepEqual(parseCSV('a\n1\n""'), [{ a: "1" }, { a: "" }]);
});

test("CSV ignores only blank physical lines and counts empty records toward row bounds", () => {
  assert.deepEqual(parseCSV("\n\nx,y\n\n,\n\n1,2\n\n"), [
    { x: "", y: "" },
    { x: "1", y: "2" }
  ]);
  assert.equal(parseCSV("x,y\n" + ",\n".repeat(5000)).length, 5000);
  assert.throws(() => parseCSV("x,y\n" + ",\n".repeat(5001)), /5000/);
});

test("Benchmark UI shows F1, per-case completions, latency distribution and denominator labels", async () => {
  const { readFile: readLocal } = await import("node:fs/promises");
  const { documentFromHTML } = await import("./ui-test-dom.mjs");
  globalThis.document = documentFromHTML(
    await readLocal(new URL("../app/index.html", import.meta.url), "utf8")
  );
  await import("../app/static/ui.mjs?feature=benchmark-metrics");
  document.getElementById("sample").onclick();
  const originalFetch = globalThis.fetch;
  // Synthetic API response for actual rendering handlers; these are not measured benchmark claims.
  const result = {
    adapter: "first_sentence",
    successful_runs: 1,
    attempted_runs: 2,
    failed_runs: 1,
    completion_ratio: 0.5,
    exact_match_accuracy: 0,
    token_f1: 2 / 3,
    all_attempt_exact_match_accuracy: 0,
    all_attempt_token_f1: 1 / 3,
    mean_latency_ms: 4,
    median_latency_ms: 4,
    min_latency_ms: 4,
    max_latency_ms: 4,
    p95_latency_ms: 4,
    errors: [],
    predictions: ["Blue.", null],
    case_results: [
      {
        case_index: 0,
        successful_runs: 1,
        attempted_runs: 2,
        failed_runs: 1,
        exact_match_accuracy: 0,
        token_f1: 2 / 3,
        all_attempt_token_f1: 1 / 3,
        median_latency_ms: 4,
        min_latency_ms: 4,
        max_latency_ms: 4
      }
    ]
  };
  globalThis.fetch = async () => ({
    ok: true,
    json: async () => ({ results: [result], limitations: [], dataset_size: 2 })
  });
  try {
    await document.getElementById("run").onclick();
    const text = document.getElementById("results").textContent;
    assert.match(text, /Token F1/);
    assert.match(text, /All-attempt token F1/);
    assert.match(text, /Median latency/);
    assert.match(text, /1\/2/);
    const session = document.getElementById("session");
    const table = session.children.find((child) => child.tagName === "table");
    const body = table.children.find((child) => child.tagName === "tbody");
    assert.equal(body.children[0].children.length, 7);
    assert.match(session.textContent, /success only/);
  } finally {
    globalThis.fetch = originalFetch;
    delete globalThis.document;
  }
});
