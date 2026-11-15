# Plugin evals

These cases check the Claude Code plugin. Each run calls a model, so this suite is not part of CI.

From the `toolkit/` directory:

```bash
claude plugin eval . --trust-plugin --no-publish --ablation none --runs 1
```

One case:

```bash
claude plugin eval . --case dimmer-aan --trust-plugin --no-publish --ablation none --runs 1
```

The cases set `runs: 1`. Pass `--runs 3` before trusting a score. Results are written to `evals/results/` and are not committed.

Mocks use invented names and documentation addresses in 192.0.2.0/24. Do not put a real name or a real address in a case or a mock.
