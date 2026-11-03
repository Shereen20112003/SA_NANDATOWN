# Sharing the contribution

## Live workbench walkthrough

Start with [the annotated screenshots](docs/DEMO.md). They show actual completed
model-backed research and evaluation runs and explain the limits of the outputs.
No coco access, model account, or local server is required to view that page.
The benchmark below remains a separate, credential-free reproducible experiment.

## Project repository

[Shereen20112003/SA_NANDATOWN](https://github.com/Shereen20112003/SA_NANDATOWN)

Suggested description:

> Many Agents, One Point of Failure: reproducible Nanda Town Lab experiments on
> dependency-aware discovery, correlated outages, and incomplete information.

This is the independent project repository, not an upstream Nanda Town PR.
The Python package and CLI are named `nanda-resilience`.

## Publish from PowerShell

For a fresh local copy with no remote, the publication commands are below.
For an already connected checkout, commit your changes and run `git push` instead.

```powershell
git add .
git diff --cached --stat
git commit -m "Add dependency-aware Nanda Town resilience experiment" -m "Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
git remote add origin https://github.com/Shereen20112003/SA_NANDATOWN.git
git push -u origin main
```

If the earlier OAuth redirect problem recurs, stop that login flow and use GitHub's supported sign-in
instructions. Never share a token or device code in a chat or commit.

The prepared ZIP is an alternative for sharing before GitHub authentication is
resolved. It contains source, tests, documentation, pinned requirements, an HTML
report, all per-run metrics, and representative evidence bundles. It does not
contain a virtual environment or private signing keys.

## Message to Vedh

Hi Vedh,

I followed the Nanda Town exercise and built a small research-oriented extension:
**Many Agents, One Point of Failure**.

It tests a case where different, correctly registered agents share the same
underlying service, so switching agent identities does not necessarily escape a
failure. The implementation uses Nanda Town's Lab engine, registry, messages,
coordination plugins, ledger, and replayable evidence bundles rather than a
separate simulator.

I approached this from my experience with agent evaluation, failure taxonomy,
and robustness under distribution shifts: the goal was to identify an interaction
that ordinary agent-level checks miss, then build a repeatable test for it.
The implementation and data are newly created and synthetic.

I compared five selection policies across shared outages, staggered
provider-local outages, and a no-outage control, with 0%, 50%, and 100% dependency
disclosure. The repository includes a 450-run campaign, costs and negative
controls, tests, and the exact limitations.

Clean-install GitHub CI also passes on Windows and Linux with Python 3.11 and
3.12, running 104 tests and 30 smoke experiments per configuration.

The most useful next collaboration would be testing how much dependency
information and coordination an agent actually needs: the current experiment has
a shared reservation view and truthful, structured dependency/failure metadata.
I'd value your feedback on whether this is a useful scenario/evaluator
contribution upstream and which assumption to relax first.

Repository: https://github.com/Shereen20112003/SA_NANDATOWN

## Five-minute demonstration

1. Open `results/published/report.html` locally.
2. Explain the topology: 12 identities, four backends, nine identities sharing one.
3. Show shared-outage completion and the random/load baselines.
4. Show the incomplete-disclosure rows and clean-operation price premium.
5. Show the independent-outage counterexample, not just the best result.
6. Run:

   ```powershell
   .\.venv\Scripts\nanda-resilience.exe verify results\published\bundles\shared-1-0-dependency
   ```

7. Explain that verification establishes internally consistent simulated
   evidence, not real-world truth, security, or production readiness.

## Upstream PR approach

This independent repository is a shareable prototype, **not an upstream PR**.
After maintainer feedback, propose a bounded contribution containing the
scenario, coordination plugins, custom roles, evaluator, and tests. Agree on the
role-registration and extension API before copying files into upstream.

Do not describe this as a deployed NANDA Index integration, an independently
validated research result, or a newly invented routing primitive.
