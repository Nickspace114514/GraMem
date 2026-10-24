# Security policy

GraMem stores personal data, so reports about leaks, scope bypasses and unsafe forgetting are taken seriously.

## Reporting a vulnerability

Please do not open a public issue. Use GitHub's private reporting:
<https://github.com/Nickspace114514/GraMem/security/advisories/new>

Include what you found, how to reproduce it with a minimal config, and the version (`pip show gramem`). Remove API keys and personal data from anything you attach. You will get an acknowledgement, and a fix or a mitigation plan as soon as it can be prepared. Credit is given if you want it.

## In scope

- A forgotten, disabled or out-of-scope memory (including originals, derived facts, profiles and graph data) that can still be recalled, exported or listed.
- One owner, contact, group or profile reading another's data.
- Secrets, tokens or personal data written to logs, exports, backups or API responses.
- Authentication or authorization gaps in the control panel API.

## Deploying safely

- Keep the profile home at mode 700 and `config.json` and data files at 600.
- Provide API keys and the graph password only through environment variables or your host's secret store.
- Bind FalkorDB to localhost, or put it on a private network with authentication.
- Only enable `trusted_cli_owner` on machines you trust, and only list verified identities under `aliases`.
