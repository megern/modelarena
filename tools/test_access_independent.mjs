import test from "node:test";
import assert from "node:assert/strict";
import vm from "node:vm";
import { readFileSync } from "node:fs";
const source = readFileSync(
  new URL("../app/static/access.js", import.meta.url),
  "utf8"
);
// A different Request constructor reproduces the cross-realm instanceof condition,
// while retaining a genuine Fetch Request with its external destination and headers.
function page(RequestConstructor = Request) {
  const nodes = [],
    calls = [];
  const document = {
    readyState: "complete",
    body: { prepend() {} },
    createElement(tag) {
      const n = {
        tag,
        children: [],
        style: {},
        textContent: "",
        value: "",
        setAttribute() {},
        append(...v) {
          this.children.push(...v);
        },
        appendChild(v) {
          this.children.push(v);
        }
      };
      nodes.push(n);
      return n;
    }
  };
  const window = {
    location: { href: "http://tool.local/", origin: "http://tool.local" },
    fetch: async (input, init) => {
      calls.push({ input, init });
      return { ok: true };
    }
  };
  vm.runInNewContext(source, {
    window,
    document,
    Request: RequestConstructor,
    Headers,
    URL
  });
  const field = nodes.find((n) => n.tag === "input"),
    save = nodes.find((n) => n.textContent.startsWith("Use key"));
  field.value = "synthetic-independent-" + "z".repeat(32);
  save.onclick();
  return { window, calls };
}
test("Cross-constructor external Request must never receive the server access key", async () => {
  class PageRequest extends Request {}
  const p = page(PageRequest),
    external = new Request("https://outside.example/upload", {
      method: "POST",
      body: "synthetic"
    });
  assert.equal(external instanceof PageRequest, false);
  await p.window.fetch(external);
  const headers = new Headers(p.calls[0].init?.headers ?? external.headers);
  assert.equal(headers.has("Authorization"), false);
});
test("Protocol-relative external URL and suffix-lookalike origin never receive key", async () => {
  const p = page();
  await p.window.fetch("//outside.example/upload");
  await p.window.fetch("http://tool.local.outside.example/upload");
  for (const call of p.calls)
    assert.equal(new Headers(call.init?.headers).has("Authorization"), false);
});

test("Own URL property on a genuine external Request cannot spoof its destination", async () => {
  const p = page(),
    external = new Request("https://outside.example/upload", {
      method: "POST",
      body: "synthetic"
    });
  Object.defineProperty(external, "url", {
    value: "http://tool.local/analyze"
  });
  await p.window.fetch(external);
  const headers = new Headers(p.calls[0].init?.headers ?? external.headers);
  assert.equal(headers.has("Authorization"), false);
});

test("Own href property on external URL and unknown objects cannot obtain implicit credential", async () => {
  const p = page(),
    external = new URL("https://outside.example/upload");
  Object.defineProperty(external, "href", {
    value: "http://tool.local/analyze"
  });
  await p.window.fetch(external);
  await p.window.fetch({
    toString() {
      return "https://outside.example/upload";
    }
  });
  for (const call of p.calls)
    assert.equal(new Headers(call.init?.headers).has("Authorization"), false);
});
