# Security

## Reporting a problem

Please report vulnerabilities privately through GitHub's
["Report a vulnerability"](https://github.com/MaXiMo000/marketpulse/security/advisories/new)
form rather than opening a public issue.

## Protections

- Every data endpoint requires a bearer token, compared in constant time; repeated failures lock the client out temporarily.
- Outside development the server refuses to start without a strong token and an explicit CORS allowlist.
- API input is validated and request bodies are size-limited; ticker symbols are restricted to a strict character set.
- Cross-origin access is limited to an explicit allowlist, and responses carry hardening headers and are never cached.
- API documentation is not served in production.
- The frontend ships a Content-Security-Policy restricted to its own files and the configured API, and keeps the token only for the browser tab.
- Secrets (API keys, database credentials) are read from the environment and never stored in the repository.
- Portfolios start in paper mode; live mode requires an explicit, dated acknowledgement, and the database rejects a live portfolio without one.

This project is a personal tool and does not provide investment advice.
