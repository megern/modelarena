export function parseCSV(text) {
  text = text.replace(/^\uFEFF/, "");
  const rows = [];
  let row = [],
    cell = "",
    quoted = false,
    closed = false,
    explicitRecord = false;
  for (let i = 0; i < text.length; i++) {
    const c = text[i];
    if (quoted) {
      if (c === '"') {
        if (text[i + 1] === '"') {
          cell += '"';
          i++;
        } else {
          quoted = false;
          closed = true;
        }
      } else cell += c;
      continue;
    }
    if (c === '"') {
      if (cell.length || closed) throw Error("CSV quote must start a field.");
      quoted = true;
      explicitRecord = true;
      continue;
    }
    if (c === "," || c === "\n" || c === "\r") {
      if (c === ",") explicitRecord = true;
      row.push(cell);
      cell = "";
      closed = false;
      if (c !== ",") {
        if (c === "\r" && text[i + 1] === "\n") i++;
        if (explicitRecord) rows.push(row);
        row = [];
        explicitRecord = false;
      }
    } else {
      if (closed) throw Error("Unexpected text after a quoted CSV field.");
      cell += c;
      explicitRecord = true;
    }
  }
  if (quoted) throw Error("CSV has an unclosed quote.");
  if (explicitRecord) {
    row.push(cell);
    rows.push(row);
  }
  if (rows.length < 2)
    throw Error("CSV needs a header and at least one data row.");
  const headers = rows.shift().map((v) => v.trim());
  if (headers.some((h) => !h) || new Set(headers).size !== headers.length)
    throw Error("CSV headers must be nonempty and unique.");
  if (headers.length > 50) throw Error("CSV supports at most 50 columns.");
  if (rows.length > 5000) throw Error("CSV supports at most 5000 rows.");
  return rows.map((r, i) => {
    if (r.length !== headers.length)
      throw Error(
        `CSV row ${i + 2} has ${r.length} fields; expected ${headers.length}.`
      );
    return Object.fromEntries(headers.map((h, j) => [h, r[j]]));
  });
}
export function inferValue(value) {
  if (value === "") return null;
  if (value === "true" || value === "false") return value === "true";
  if (/^-?(?:0|[1-9]\d*)(?:\.\d+)?(?:e[+-]?\d+)?$/i.test(value)) {
    const n = Number(value);
    if (!Number.isFinite(n) || Math.abs(n) > 1e100)
      throw Error("Numeric magnitude exceeds 1e100. Rescale this CSV column.");
    return n;
  }
  return value;
}
export function csvText(rows) {
  const encode = (v) => {
    let s = v == null ? "" : String(v);
    if (typeof v === "string" && /^[\s]*[=+\-@]/.test(s)) s = "'" + s;
    return '"' + s.replace(/"/g, '""') + '"';
  };
  return rows.map((r) => r.map(encode).join(",")).join("\r\n");
}
export const $ = (id) => document.getElementById(id);
export function el(tag, text, cls) {
  const n = document.createElement(tag);
  if (text !== undefined) n.textContent = String(text);
  if (cls) n.className = cls;
  return n;
}
export function clear(n) {
  n.replaceChildren();
}
export function metric(parent, label, value, detail) {
  const n = el("div", undefined, "metric");
  n.append(el("small", label), el("strong", value));
  if (detail) n.append(el("small", detail));
  parent.append(n);
}
export function table(parent, headers, rows) {
  const t = el("table"),
    head = el("thead"),
    hr = el("tr");
  for (const h of headers) hr.append(el("th", h));
  head.append(hr);
  t.append(head);
  const body = el("tbody");
  for (const row of rows) {
    const tr = el("tr");
    for (const value of row)
      tr.append(el("td", value == null ? "Not defined" : value));
    body.append(tr);
  }
  t.append(body);
  parent.append(t);
  return t;
}
export function number(value, digits = 3) {
  return value == null
    ? "Not defined"
    : Number(value).toLocaleString(undefined, {
        maximumFractionDigits: digits
      });
}
export function percent(value) {
  return value == null ? "Not defined" : number(value * 100, 1) + "%";
}
export function download(name, content, type = "application/json") {
  const url = URL.createObjectURL(new Blob([content], { type }));
  const a = el("a");
  a.href = url;
  a.download = name;
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
export async function readFile(file) {
  if (!file) throw Error("Choose a file.");
  if (file.size > 2097152)
    throw Error("File exceeds 2 MiB. Split the dataset.");
  return file.text();
}
export function errorMessage(data) {
  if (Array.isArray(data.detail))
    return data.detail
      .map((x) => `${x.loc.filter((v) => v !== "body").join(".")}: ${x.msg}`)
      .join("\n");
  return String(data.detail || "Request failed.");
}
export async function analyze(payload) {
  const response = await fetch("/analyze", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload)
  });
  const data = await response.json();
  if (!response.ok) throw Error(errorMessage(data));
  return data;
}
export function status(text, error = false) {
  $("status").textContent = text;
  $("status").className = error ? "status error" : "status notice";
}
export function resultDetails(parent, result) {
  const d = el("details"),
    p = el("pre", JSON.stringify(result, null, 2));
  d.append(el("summary", "Raw calculation output"), p);
  parent.append(d);
}
export function limitations(parent, lines) {
  const div = el("div", undefined, "notice");
  for (const line of lines) div.append(el("p", line));
  parent.append(div);
}
export function setupDownloads(getInput, getReport, prefix) {
  $("export-input").onclick = () => {
    try {
      download(prefix + "-input.json", JSON.stringify(getInput(), null, 2));
    } catch (e) {
      status(e.message, true);
    }
  };
  $("export-report").onclick = () => {
    const r = getReport();
    if (!r) {
      status("Run an analysis before exporting a report.", true);
      return;
    }
    download(
      prefix + "-report.json",
      JSON.stringify(
        {
          application: prefix,
          version: "0.2.0",
          generated_at: new Date().toISOString(),
          ...r
        },
        null,
        2
      )
    );
  };
}
