// Minimal DOM adapter for exercising actual UI handlers in Node. It does not replace browser QA.
export class Element {
  constructor(tag) {
    this.tagName = tag;
    this.children = [];
    this.value = "";
    this.checked = false;
    this.className = "";
    this._text = "";
    this.listeners = {};
    this.classList = { remove: () => {} };
  }
  set textContent(value) {
    this._text = String(value);
    this.children = [];
  }
  get textContent() {
    return this._text + this.children.map((x) => x.textContent).join("");
  }
  append(...children) {
    this.children.push(...children);
  }
  replaceChildren(...children) {
    this._text = "";
    this.children = [...children];
  }
  addEventListener(type, handler) {
    this.listeners[type] = handler;
  }
  dispatch(type) {
    (this["on" + type] || this.listeners[type])?.({ target: this });
  }
  click() {
    this.onclick?.();
  }
  querySelector(selector) {
    return this.querySelectorAll(selector)[0] || null;
  }
  querySelectorAll(selector) {
    const matches = (node) => {
      if (selector.startsWith(".")) {
        const [name, state] = selector.slice(1).split(":");
        return (
          node.className.split(" ").includes(name) && (!state || node.checked)
        );
      }
      return node.tagName === selector;
    };
    const found = [];
    function visit(node) {
      for (const child of node.children) {
        if (matches(child)) found.push(child);
        visit(child);
      }
    }
    visit(this);
    return found;
  }
}

export function documentFromHTML(html) {
  const ids = new Map();
  const roots = [];
  for (const match of html.matchAll(
    /<([a-z]+)\b([^>]*\bid="([^"]+)"[^>]*)>/g
  )) {
    const node = new Element(match[1]);
    node.value = match[2].match(/\bvalue="([^"]*)"/)?.[1] || "";
    node.checked = /\bchecked\b/.test(match[2]);
    ids.set(match[3], node);
    roots.push(node);
  }
  for (const match of html.matchAll(/<input\b[^>]*>/g)) {
    if (!/class="tool"/.test(match[0])) continue;
    const node = new Element("input");
    node.className = "tool";
    node.value = match[0].match(/\bvalue="([^"]*)"/)?.[1] || "";
    roots.push(node);
  }
  const wrapper = new Element("body");
  wrapper.append(...roots);
  return {
    createElement: (tag) => new Element(tag),
    getElementById: (id) => ids.get(id),
    querySelectorAll: (selector) => wrapper.querySelectorAll(selector),
    snapshot: () =>
      [
        ...wrapper.querySelectorAll("input"),
        ...wrapper.querySelectorAll("textarea")
      ].map((x) => [x.value, x.checked])
  };
}

export function deferred() {
  let resolve, reject;
  const promise = new Promise((yes, no) => {
    resolve = yes;
    reject = no;
  });
  return { promise, resolve, reject };
}
