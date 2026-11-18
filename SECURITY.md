# Security

## Reporting a problem

Please report vulnerabilities privately through GitHub's
["Report a vulnerability"](https://github.com/MaXiMo000/marketpulse/security/advisories/new)
form rather than opening a public issue.

## Protections

- API input is validated; ticker symbols are restricted to a strict character set.
- Cross-origin access is limited to an explicit allowlist.
- Secrets (API keys, database credentials) are read from the environment and never stored in the repository.
- Portfolios start in paper mode; live trading is gated behind an explicit, dated acknowledgement (planned, see SPEC.md).

This project is a personal tool and does not provide investment advice.
