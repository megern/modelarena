/* The key stays in this page's memory and is attached only to same-origin requests. */
(() => {
  "use strict";
  const nativeFetch = window.fetch.bind(window);
  let accessKey = "";
  function nativeGetter(prototype, name) {
    for (
      let current = prototype;
      current;
      current = Object.getPrototypeOf(current)
    ) {
      const descriptor = Object.getOwnPropertyDescriptor(current, name);
      if (descriptor && descriptor.get) return descriptor.get;
    }
    return null;
  }
  const requestURL = nativeGetter(Request.prototype, "url");
  const requestHeaders = nativeGetter(Request.prototype, "headers");
  const urlHref = nativeGetter(URL.prototype, "href");
  window.fetch = (input, init) => {
    if (!accessKey) return nativeFetch(input, init);
    let address, originalHeaders;
    if (typeof input === "string") address = input;
    else {
      try {
        address = requestURL.call(input);
        originalHeaders = requestHeaders.call(input);
      } catch {
        try {
          address = urlHref.call(input);
        } catch {
          return nativeFetch(input, init);
        }
      }
    }
    const url = new URL(address, window.location.href);
    if (url.origin !== window.location.origin) return nativeFetch(input, init);
    const headers = new Headers(originalHeaders);
    new Headers(init && init.headers).forEach((value, name) =>
      headers.set(name, value)
    );
    if (!headers.has("Authorization"))
      headers.set("Authorization", "Bearer " + accessKey);
    return nativeFetch(input, { ...init, headers });
  };
  function install() {
    const details = document.createElement("details");
    details.className = "server-access";
    details.style.cssText =
      "margin:12px auto;padding:10px 16px;max-width:1120px;border:1px solid #ced9e2;border-radius:8px;font:14px system-ui;background:#f6f9fb;color:#173246";
    const summary = document.createElement("summary");
    summary.textContent = "Server access / الدخول إلى الخادم";
    const label = document.createElement("label");
    label.textContent =
      "Access key (only for a protected server) / مفتاح الوصول";
    const field = document.createElement("input");
    field.type = "password";
    field.autocomplete = "off";
    field.spellcheck = false;
    field.setAttribute("aria-label", "Server access key");
    const save = document.createElement("button");
    save.type = "button";
    save.textContent = "Use key / استخدام المفتاح";
    const clear = document.createElement("button");
    clear.type = "button";
    clear.textContent = "Clear / مسح";
    const status = document.createElement("p");
    status.setAttribute("role", "status");
    status.textContent =
      "Optional. Kept in page memory only; a reload clears it. / اختياري؛ لا يُحفظ بعد تحديث الصفحة.";
    save.onclick = () => {
      accessKey = field.value;
      field.value = "";
      status.textContent = accessKey
        ? "Key loaded for this page. Retry your action. / تم تحميل المفتاح لهذه الصفحة؛ أعد المحاولة."
        : "No key loaded. / لم يُحمّل مفتاح.";
    };
    clear.onclick = () => {
      accessKey = "";
      field.value = "";
      status.textContent = "Key cleared. / مُسح المفتاح.";
    };
    label.appendChild(field);
    details.append(summary, label, save, clear, status);
    document.body.prepend(details);
  }
  if (document.readyState === "loading")
    document.addEventListener("DOMContentLoaded", install, { once: true });
  else install();
})();
