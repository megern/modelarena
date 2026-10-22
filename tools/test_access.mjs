import test from "node:test";
import assert from "node:assert/strict";
import vm from "node:vm";
import { readFileSync, existsSync } from "node:fs";
const installed = new URL("../app/static/access.js", import.meta.url);
const source = readFileSync(
  existsSync(installed) ? installed : new URL("./access.js", import.meta.url),
  "utf8"
);
function page(readyState = "complete") {
  const nodes = [],
    calls = [],
    listeners = {};
  function element(tag) {
    const n = {
      tag,
      children: [],
      value: "",
      textContent: "",
      style: {},
      attributes: {},
      append(...children) {
        this.children.push(...children);
      },
      appendChild(child) {
        this.children.push(child);
      },
      setAttribute(k, v) {
        this.attributes[k] = v;
      }
    };
    nodes.push(n);
    return n;
  }
  const document = {
    readyState,
    createElement: element,
    body: {
      prepend(n) {
        this.child = n;
      }
    },
    addEventListener(name, fn) {
      listeners[name] = fn;
    }
  };
  const window = {
    location: { href: "http://tool.local/", origin: "http://tool.local" },
    fetch: async (input, init) => {
      calls.push({ input, init });
      return { ok: true };
    }
  };
  Object.defineProperty(window, "localStorage", {
    get() {
      throw Error("No persistent key storage");
    }
  });
  Object.defineProperty(window, "sessionStorage", {
    get() {
      throw Error("No persistent key storage");
    }
  });
  vm.runInNewContext(source, { window, document, Request, Headers, URL });
  if (readyState === "loading") listeners.DOMContentLoaded();
  const field = nodes.find((n) => n.tag === "input"),
    save = nodes.find((n) => n.textContent === "Use key / استخدام المفتاح"),
    clear = nodes.find((n) => n.textContent === "Clear / مسح");
  return { window, document, nodes, calls, field, save, clear };
}
const key = () => "synthetic-" + "x".repeat(32);
test("Default page does not attach a credential or change request bodies", async () => {
  const p = page();
  const init = { method: "POST", body: '{"rows":[]}' };
  await p.window.fetch("/analyze", init);
  assert.equal(p.calls[0].init, init);
  assert.equal(p.field.type, "password");
});
test("Actual key form affects same-origin requests only and clears its field", async () => {
  const p = page("loading");
  p.field.value = key();
  p.save.onclick();
  assert.equal(p.field.value, "");
  await p.window.fetch("/analyze", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: "{}"
  });
  const init = p.calls[0].init;
  assert.equal(init.headers.get("Authorization"), "Bearer " + key());
  assert.equal(init.headers.get("Content-Type"), "application/json");
  assert.equal(init.body, "{}");
  await p.window.fetch("https://other.example/analyze", { method: "POST" });
  assert.equal(p.calls[1].init.headers, undefined);
  assert.ok(!JSON.stringify(p.document.body).includes(key()));
});
test("Explicit authorization and Request headers are preserved", async () => {
  const p = page();
  p.field.value = key();
  p.save.onclick();
  await p.window.fetch(
    new Request("http://tool.local/jobs/private", {
      headers: { "X-Test": "preserved" }
    }),
    { headers: { Authorization: "Bearer caller-owned" } }
  );
  assert.equal(p.calls[0].init.headers.get("X-Test"), "preserved");
  assert.equal(
    p.calls[0].init.headers.get("Authorization"),
    "Bearer caller-owned"
  );
});
test("Clear and page reload remove the credential", async () => {
  const p = page();
  p.field.value = key();
  p.save.onclick();
  p.clear.onclick();
  await p.window.fetch("/analyze");
  assert.equal(p.calls[0].init, undefined);
  const fresh = page();
  await fresh.window.fetch("/jobs/private");
  assert.equal(fresh.calls[0].init, undefined);
});
