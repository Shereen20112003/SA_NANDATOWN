# Many Agents, One Point of Failure

**A reproducible Nanda Town Lab experiment on shared dependencies in agent discovery.**

Project repository: [Shereen20112003/SA_NANDATOWN](https://github.com/Shereen20112003/SA_NANDATOWN).

[Clean-install CI verification](https://github.com/Shereen20112003/SA_NANDATOWN/actions/runs/41619744094):
104 tests and 30 smoke experiments passed on each Windows/Linux and Python
3.11/3.12 combination.

Twelve service agents can look like twelve alternatives while nine depend on the
same backend. This project asks whether dependency-aware selection improves
completion under shared failures, what it costs, and how the benefit changes when
dependency declarations are incomplete.

This is an independent research prototype, not an MIT-endorsed project, a
production routing system, or a claim of a novel distributed-systems primitive.

## Connection to my work

My relevant experience is in agent evaluation: finding behaviors that existing
tests miss, classifying failures, and measuring robustness under distribution
shifts. This contribution applies that evaluation-centered approach to
agent-to-agent infrastructure.

The coverage gap is specific: checking each agent's identity, capability, or
isolated success does not exercise a shared dependency failing across several
otherwise distinct agents. The experiment adds that condition, separates
provider-local from backend-wide failures, and checks both task outcomes and the
evidence supporting them.

This is newly implemented synthetic work. It does not incorporate employer code,
private datasets, internal evaluation results, or unpublished project artifacts.
It is not an automatic hidden-test generator; that would be a separate extension.

## Start with the evidence

The shareable release includes:

- [Interactive-free HTML report](results/published/report.html): open the downloaded
  file in a browser; no server, account, JavaScript, or external assets required.
- [Complete results](results/published/summary.json) and [per-run CSV](results/published/runs.csv).
- [Findings and limitations](FINDINGS.md).
- [Three representative native Lab bundles](results/published/bundles):
  price selection, load balancing, and dependency-aware selection under the same
  fully disclosed shared-outage scenario and seed.

The HTML renders measured results, not hard-coded claims. GitHub's file view does
not render HTML; download it with its neighboring JSON/CSV files, or serve the
repository locally.

## What is actually integrated with Nanda Town?

The extension uses the upstream **Lab engine**, not an independent simulator:

```text
buyer --discovery--> Nanda Town owned registry
buyer --selection--> replaceable coordination plugin
buyer --service request--> provider --compute request--> shared backend
buyer <--service result--- provider <--compute result--- shared backend
buyer --successful settlement--> Nanda Town ledger
                         |
                    events + intents
                         |
            versioned trace evaluator + evidence bundle
```

- Four custom roles: workload clock, buyers, service providers, backend services.
- Five plugins in the existing `coordination` layer; the default contract-net
  methods remain available through inheritance.
- Signed registration through `index.owned.v1` and messages through the standard
  communication, authorization, and transport layers.
- Actual simulated backend occupancy, service times, request/result messages,
  bounded retries, and integer-cent ledger payments.
- The `resilience.v2` evaluator checks workload coverage, policy decisions,
  declared outages, capacity, request/result bindings, attempt budgets, settlement,
  and completion from the exported profile and trace.
- Upstream manifests, attestation, report rendering, and replay verification.

Upstream is pinned to
[`b7adc6121868742cf0f00cfebbf2d38bdb349057`](https://github.com/projnanda/nandatown/commit/b7adc6121868742cf0f00cfebbf2d38bdb349057).
No upstream source changes are required.

## Install

Python 3.11 or 3.12 and Git are required. No model credentials or API spending.

### Windows PowerShell

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.lock
.\.venv\Scripts\python.exe -m pip install -e .
.\.venv\Scripts\python.exe -m pytest -q
```

If Python is managed with `uv` instead:

```powershell
uv venv --python 3.12
uv pip install -r requirements.lock
uv pip install -e .
```

The portable requirements file pins and hashes registry-hosted transitive and
development dependencies. The second installation command installs the project
and its immutable Git-pinned Nanda Town dependency from the project manifest.
Do not add `--no-deps` to that command on a clean environment: pip cannot put a
Git dependency in the same hash-checked requirements file.
Use your organization's configured package index if direct PyPI access is
unavailable; do not disable TLS verification. The local `uv.lock` is ignored
because it can embed environment-specific package-index URLs.

### macOS / Linux

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.lock
python -m pip install -e .
python -m pytest -q
```

Activate the environment or prefix the commands below with its executable path.
On PowerShell, for example, use `.\.venv\Scripts\nanda-resilience.exe`.

## Run one experiment

```powershell
.\.venv\Scripts\nanda-resilience.exe run --condition shared --policy dependency --seed 7 --disclosure 1 --out results\single
.\.venv\Scripts\nanda-resilience.exe verify results\single
```

Outputs are written to a **new** directory. Existing evidence is never silently
overwritten. `verify` replays the evaluator and recomputes metrics; it does not
trust the auxiliary `metrics.json`.

Use this extension's `verify` command for custom bundles: native Nanda Town's
standalone verifier does not automatically import third-party evaluators.
The wrapper registers the installed evaluator before invoking upstream
verification. It never imports executable code named by an untrusted bundle.

Signatures protect bundle integrity, not the truth of dependency declarations.
Demo signing keys are generated in a temporary directory and are not published.
No personal Nanda Town keystore is used by the wrapper.
Published bundles are marked binary in `.gitattributes` to preserve their exact
signed bytes across Windows/Linux checkouts and prevent invalid text merges.
Inspect their readable JSON files directly rather than editing them.

## Run the full campaign

```powershell
.\.venv\Scripts\nanda-resilience.exe campaign --out results\campaign --seeds 0 1 2 3 4 5 6 7 8 9 --disclosures 0 0.5 1
```

This runs **450 experiments**: 10 seeds x 3 failure conditions x 3 disclosure
levels x 5 policies. Expect several minutes, depending on the machine.

Every run is evaluated. By default, full bundles are retained for the first seed
in each condition/disclosure/policy combination (45 bundles); all 450 per-run
metrics and logical trace fingerprints are retained. Use `--keep-all` to retain
every bundle. Unretained runs can be regenerated from their settings and seed.

The same seed gives the same logical experiment and metrics. Bundle IDs, signing
keys, and wall-clock attestation metadata differ; files are **not byte-identical**.
The logical trace fingerprint excludes those fields but includes the selected
policy, so oracle and dependency traces have different fingerprints even if they
make identical decisions.

## Run through the native Nanda Town CLI

From the repository root with the extension installed:

```powershell
.\.venv\Scripts\nanda-resilience.exe scenario --condition shared --policy price --seed 7 --disclosure 1 --out results\shared.yaml
$env:NANDATOWN_HOME = Join-Path (Get-Location) ".town-home"
.\.venv\Scripts\nandatown.exe run results\shared.yaml --plugin plugin.py --layer coordination=resilience.dependency.v1 --out results\native
```

Verify the resulting run subdirectory with `nanda-resilience verify`.
Native bundle profiles can contain the absolute plugin path. The published
wrapper-generated bundles deliberately avoid machine-specific plugin paths.

The custom buyer uses the same `TownAPI._engine.layers` access pattern found in
upstream reference agents to invoke the extended coordination method. That is an
upstream implementation interface, not a promise of a stable public API; hence
the pinned revision and native-integration regression test.

## Experimental design

### Population and workload

- 12 providers: nine share backend 0; three use backends 1, 2, and 3.
- Shared-backend providers cost 10 cents per completed task; independent providers
  cost 12, 14, and 16 cents.
- 8 buyers x 20 tasks; cohorts arrive at logical times 1, 3, ..., 39.
- At most 3 attempts per task; previously tried provider identities are excluded.
- Backend service duration: 0.35 logical units. Message latency: 0.1 per leg.
- Each backend admits up to 12 simultaneous requests. Rejected attempts consume
  messages and retry budget but are not charged.
- All providers have equal initial reputation. This version does not learn or
  update reputation; price breaks quality ties. It does not claim to demonstrate
  an emergent reputation feedback loop.

### Five policies

| Policy | Selection rule |
|---|---|
| `price` | Lowest price, then reputation, then seeded task-specific tie break. |
| `random` | Seeded uniform hash ranking among untried provider identities. |
| `load` | Fewest outstanding provider reservations, then price. |
| `dependency` | Avoid groups that failed this task; then minimize outstanding group reservations, provider reservations, and price. |
| `oracle` | The same dependency policy with complete true dependency labels, but no knowledge of outages or future results. |

The oracle is an **information-rich comparator, not a mathematical optimum**.
At full disclosure it should make the same decisions as `dependency`.
Reservations are shared across buyers and released on each attempt result.
Failed-group memory is per task, not a global failure detector. A reported backend
outage or capacity rejection marks the dependency group; a provider-local outage
excludes only that provider identity. This relies on truthful, structured failure
attribution from the synthetic services, not inference from a generic timeout.

Unknown dependencies share one conservative `unknown` group. They are never
assumed to represent independent backends. At 0% disclosure, this removes the
candidate policy's dependency-information advantage.

### Three failure conditions

| Condition | Fault |
|---|---|
| `clean` | No outage: measures normal-operation cost and concentration. |
| `shared` | Backend 0 unavailable during [12, 28), affecting nine providers. |
| `independent` | Nine seeded provider outages of duration 16, with separately sampled start times in [4, 20]. |

Shared and independent conditions have equal **aggregate provider downtime**
(144 provider-time units). They do not have equal instantaneous unavailable
capacity or equal exposure for every task.

Disclosure masks are nested and seeded independently from outage schedules.
Policies and disclosure conditions share the same underlying world for a seed.
Selection uses a separate task/attempt/provider hash, so policy randomness does
not alter faults.

### Metrics

- Overall completion and completion for tasks **created** in [12, 28).
  A task created before recovery can finish after recovery.
- Attempts per submitted task; retries that revisit an actual dependency.
- Charged cents per successful task and total spending. Cost-per-success is
  conditional on success; it is not a full economic welfare estimate.
- Nearest-rank p95 latency among successful tasks; failures are excluded.
- Pre-stress Herfindahl-Hirschman concentration over agent identities and actual
  dependency identities, computed over attempted requests before t=12.
- Recovery: time from the last outage end to the first of two consecutive
  post-outage cohorts achieving at least 90% completion. `null` means not observed
  or not applicable; see the condition and observed-count fields.
- Paired-seed effects and 95% percentile bootstrap intervals, 2,000 resamples.
  These summarize this synthetic experiment, not deployment guarantees.

## Scope and next research step

This establishes a reproducible failure case and an information/cost ablation,
not a solved decentralized discovery protocol. The coordinator has a consistent
global reservation view; its own failure, synchronization cost, and latency are
not modeled. Dependency declarations are truthful when present, static,
single-hop, and unverified beyond their attributed signature.

No LLM inference, model-quality correlations, dishonest declarations, dependency
inference, hidden multi-hop graphs, elastic capacity, request loss, or hostile
code execution is claimed. Transport-fault scenarios are rejected by this
version's evaluator rather than mislabeled as tested.

The useful next step is to compare this shared view against delayed,
organization-local views and quantify the information and coordination cost
needed to approach its result. A subsequent Track implementation should exercise
real shared services and real process failures. Lab plugins do not automatically
extend Track or the deployed NANDA Index.

Information separation is a property of these policy implementations, not a
security boundary: Lab plugins run as trusted Python code and can access the
engine. The candidate policy does not read hidden dependency configuration;
the explicitly labeled oracle does. Do not execute an unknown third-party
plugin simply because it has a scenario or an evidence bundle.

## Related work and attribution

- [Nanda Town](https://github.com/projnanda/nandatown), Apache-2.0:
  engine, layers, evidence model, and contribution conventions.
- Raskar et al., [Beyond DNS: NANDA Index and Verified AgentFacts](https://arxiv.org/abs/2507.14263),
  July 2025: dynamic discovery, capability metadata, and privacy-sensitive access.
- Raskar et al., [Upgrade or Switch](https://arxiv.org/abs/2506.12003),
  June/July 2025: infrastructure requirements for independently operated agents.
- [NANDA IEEE TPS 2026 workshop](https://projectnanda.org/workshops/ieeetps26/):
  current discovery, delegation, containment, provenance, and testbed work.
- [RFC 4202, Shared Risk Link Groups](https://www.rfc-editor.org/rfc/rfc4202.html):
  established modeling of distinct resources exposed to a shared failure.
- Dean and Barroso, [The Tail at Scale](https://cacm.acm.org/research/the-tail-at-scale/),
  2013: tail tolerance and the limitations of replicas with correlated behavior.

Shared-risk routing, load balancing, and retry controls are established ideas.
The proposed contribution is the **Nanda Town integration, failure scenario,
auditable evaluation, and incomplete-information comparison**. Priority or
research novelty requires a broader literature review and maintainer feedback.

Project code is MIT-licensed. The upstream dependency retains its Apache-2.0
license. All experimental data is synthetic. Development was AI-assisted; the
tests and recorded experiments are executable evidence, not independent review.
