# Security policy

This v0.1 engineering tool runs locally without authentication. Bind to localhost. Before external hosting, configure authentication, TLS, rate limits and monitoring. Do not submit secrets. Inputs are capped at 2 MiB, nesting at 32 levels and numeric magnitude at 1e100; application-specific bounds also apply. Containers run nonroot with a read-only filesystem, dropped capabilities, 512 MiB memory and one CPU in compose.

CI blocks on unit/API/container tests, Bandit, runtime dependency audit, secrets scan and all known MEDIUM/HIGH/CRITICAL container vulnerabilities, including unfixed advisories. Complete local Trivy reports are saved; a clean scan is evidence only against the database snapshot used, not a guarantee against unknown vulnerabilities. Synthetic fixtures are not field security validation. Required branch checks must also be enabled on GitHub.

Report security problems through a private GitHub vulnerability report where enabled. Avoid posting exploitable details or credentials in public issues.

The secrets scanner has one narrow exception: the public CPython release-signing fingerprint in `evidence/trivy-image.json` image metadata. The exception requires both that path and exact public fingerprint; private keys and other tokens remain blocked.
