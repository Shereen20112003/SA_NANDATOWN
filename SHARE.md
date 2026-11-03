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

This is the independent project repository. The upstream contribution is
[Nanda Town PR #318](https://github.com/projnanda/nandatown/pull/318), submitted
for review, not merged.
The Python package and CLI are named `nanda-resilience`.

## Verification and scope

[Hosted clean-install CI](https://github.com/Shereen20112003/SA_NANDATOWN/actions/runs/41708428755)
passed on Windows and Linux with Python 3.11 and 3.12: 190 tests, 30 deterministic
smoke experiments, and a wheel build per configuration.

The workbench's real coco-backed research and evaluation runs were verified
separately; CI uses mocked model providers. The walkthrough shows saved real-run
screenshots, not a publicly hosted interactive service. The application runs
locally, and a real Azure call has not yet been verified.

The separate deterministic benchmark includes 450 published runs / 72,000 tasks
across five policies, three failure conditions, three dependency-disclosure
levels, and ten seeds. Its results include costs and negative controls, not just
the favorable shared-outage case.

For current source, use GitHub's **Code > Download ZIP** or clone the repository.
Local credentials and workbench run journals are not published.

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

## Upstream contribution

[PR #318](https://github.com/projnanda/nandatown/pull/318) proposes the full
opt-in deterministic package: scenario generation, coordination policies,
custom roles, evaluator, evidence verification, campaign/report tooling,
documentation, and 108 experiment/integration tests. It does not include the
live Azure/coco workbench or generated campaign bundles.

Local upstream validation passed those 108 tests and 305 existing upstream
tests. Three Windows-sensitive upstream failures were reproduced against clean
upstream HEAD and are documented in the PR. Submission is not maintainer
acceptance; review and merge remain with the Nanda Town maintainers.

A useful follow-up collaboration would relax the experiment's truthful
dependency metadata or shared reservation assumptions.

Do not describe this as a deployed NANDA Index integration, an independently
validated research result, or a newly invented routing primitive.
