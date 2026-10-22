# Private-server operation

Version 0.4 adds optional shared-key API access and per-process compute admission. Localhost binding remains the default. These controls do not implement multi-user identity, per-user isolation, distributed rate limits, TLS or durable storage.

Set `VENTURELAB_API_KEY` in the server environment to 32–256 printable ASCII characters without whitespace. Supply your own secret; do not commit it or include it in a URL. Docker Compose forwards this variable. When unset or empty, the application retains local mode. `GET /health` returns `X-Access-Mode: token` when protection is active and `local` otherwise; no key is returned.

Use `Authorization: Bearer <your-server-key>` on private API requests, including job status/results. The UI has a **Server access** panel. Its key stays only in page memory, is attached only to same-origin requests, and disappears on reload. Entering a browser key does not turn server protection on; the server environment does. Public GET/HEAD pages, guides, schemas, assets and health remain accessible.

`VENTURELAB_MAX_INFLIGHT` defaults to 1 and accepts 1–4. Excess concurrent POST/PUT/PATCH requests receive HTTP 429 with Retry-After. This is a per-process admission limit, not a global user quota. Background workers, where supported, have their own explicit queue bounds. Invalid nonempty key/capacity configurations fail closed. API responses use no-store cache headers.

For an internet-accessible service, supply HTTPS, identity and user-specific authorization, abuse controls, monitoring, backups and operating procedures, then validate load and recovery. A shared key alone does not provide those capabilities. Windows/macOS/Linux users can use Docker Compose; exact tested platforms and current release evidence are recorded in the versioned evidence and QA report. Native Python requires Python 3.12+ and the declared dependencies.
