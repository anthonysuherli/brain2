# Security Policy — brain2

## Reporting a vulnerability

**Do not open a public GitHub issue for security problems.**

Report vulnerabilities privately by email to **anthonysuherli@gmail.com** with
the subject line `brain2 security`. If you use GitHub's private vulnerability
reporting ("Report a vulnerability" under the repo's Security tab), that works
too.

Please include:

- A description of the issue and the impact you believe it has.
- Steps to reproduce (a proof-of-concept is ideal).
- The version / commit you tested against.
- Any suggested remediation, if you have one.

## What to expect

- **Acknowledgement** within 5 business days.
- A good-faith effort to assess and, where warranted, fix the issue.
- Credit in the release notes if you'd like it (or anonymity if you prefer).

This is a solo-maintained open-source project provided "AS IS" with no warranty
(see [LICENSE](LICENSE)). There is no paid bug bounty and no contractual SLA;
the timelines above are best-effort.

## Coordinated disclosure

Please give a reasonable window to ship a fix before disclosing publicly. We
aim for **90 days** from report to public disclosure, sooner if a fix ships
earlier. We will keep you updated and credit your report.

## Scope notes specific to brain2

- **Local tier is loopback-only by design.** The free/local tier binds
  `127.0.0.1` and disables auth on purpose (single user, single device). A
  report that "the local API has no auth" is expected behavior, not a
  vulnerability — unless you can show it binding a non-loopback interface or
  being reachable off-device.
- **Captured context may contain secrets.** brain2 snapshots workspace state
  (git diffs, open files, hypotheses). If you find brain2 transmitting or
  storing data it shouldn't, or leaking one user's captures to another on the
  cloud tier, that is in scope and we want to hear about it.
- **Cloud tenancy.** Cross-tenant data exposure (one org reading another org's
  findings or activity graph) is high severity — report it directly.
- **Secrets in git history.** If you find committed credentials (Supabase keys,
  JWT secrets, tokens) in this repository's history, report privately rather
  than filing publicly; rotation may be needed before disclosure.
