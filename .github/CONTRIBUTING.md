# Contributing to brain2

Thanks for your interest in brain2. Contributions are welcome under the terms
below. These terms exist to keep the project clean of IP disputes — they
protect both you and the maintainer.

## License of contributions (inbound = outbound)

brain2 is licensed under the [MIT License](../LICENSE). **By submitting a
contribution (a pull request, patch, or any code/docs/content) you agree that
your contribution is licensed to the project and to everyone who receives the
project under the same MIT License.** This is the "inbound = outbound" rule:
what comes in is governed by the same license that goes out.

You retain copyright to your contribution. You are simply granting the project
the right to use and redistribute it under MIT.

## Sign your work — Developer Certificate of Origin (DCO)

brain2 uses the [Developer Certificate of Origin](DCO) (DCO 1.1) instead of a
Contributor License Agreement. The DCO is a lightweight, per-commit
certification that **you have the right to submit the code you are
contributing** and that you agree to license it under MIT.

To certify a commit, sign it off:

```bash
git commit -s -m "your message"
```

This appends a line to your commit message:

```
Signed-off-by: Your Name <your.email@example.com>
```

By signing off you certify the statements in the [DCO](DCO). Use your real name
(no anonymous or pseudonymous sign-offs). Unsigned commits may be asked to be
amended before merge.

## What you're certifying matters

Do **not** contribute code you don't have the right to license under MIT —
that includes code copied from copyleft (GPL/AGPL) projects, code owned by an
employer who hasn't cleared it, or AI-generated code whose provenance you can't
stand behind. If your employer owns your work output, get written permission
before contributing on your own behalf.

## How to contribute

1. Open an issue first for anything non-trivial, so we can agree on the
   approach before you build it.
2. Fork, branch, and keep changes focused — one concern per PR.
3. Match the surrounding code's style (see `CLAUDE.md` for conventions; imports
   are always `from brain2.*`, never `from delapan.*`).
4. Run the backend tests before opening a PR:
   ```bash
   cd backend && .venv/bin/pytest
   ```
5. Sign off your commits (`git commit -s`).
6. Open the PR against `main` with a clear description of *why*, not just *what*.

## Security issues

Do **not** open a public issue for a security vulnerability. Follow the
disclosure process in [SECURITY.md](SECURITY.md).

## Code of conduct

Participation is governed by the [Code of Conduct](CODE_OF_CONDUCT.md).
