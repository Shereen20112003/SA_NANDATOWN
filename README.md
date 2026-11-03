# Many Agents, One Point of Failure

**A reproducible Nanda Town Lab experiment on shared dependencies in agent discovery.**

This repository also includes **Nanda Workbench**, a light-themed local application
for source-based research and model-generated behavioral evaluations using real
Azure OpenAI or coco/Copilot calls. The deterministic experiment and live application are
separate modes; the original report is not a live-agent demonstration.

**[View the real-agent demo walkthrough](docs/DEMO.md)**: annotated screenshots
of completed research and evaluation runs, with no model account or installation
needed to view them.

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
The benchmark is not an automatic hidden-test generator. The separate workbench
can ask a model to generate challenging cases, run a target model, and judge its
responses, but that does not establish that the generated cases are novel,
exhaustive, or correctly labeled.

## Live-agent application

**Verification status:** on November 3, 2026, two real coco-backed workflows
completed through the local browser UI using Claude Haiku 4.5: a one-source
research brief (3 model steps, 7,247 reported tokens) and a one-case evaluation
(4 steps, 4,403 tokens). Both took about 133 seconds on the verification machine.
Source quotations, judgment quotation, and signed-message send/delivery counts
were checked against the saved evidence. Draft isolation, reload persistence,
history, JSON export, and a paused-backend failure with zero model calls were
also verified. Earlier failed integration attempts remain in local history.
A successful real Azure run has not yet been verified.
The linked hosted CI results above apply to the previously published benchmark,
not the later workbench addition. Current checks are listed in the
[Actions tab](https://github.com/Shereen20112003/SA_NANDATOWN/actions).

After installing the project as described below, create a **local, ignored**
`.env` file using `.env.example`. Never commit credentials or paste them into an
issue, chat, exported run, or browser form.

```dotenv
AZURE_OPENAI_ENDPOINT=https://YOUR-RESOURCE.openai.azure.com/
AZURE_OPENAI_API_KEY=YOUR-LOCAL-KEY
AZURE_OPENAI_DEPLOYMENT=YOUR-DEPLOYMENT-NAME
```

In Azure Portal, select an authorized Azure OpenAI resource and open **Keys and
Endpoint**. In Foundry's deployment management, copy the actual deployment name,
not just the underlying model name. Use a deployment supporting the Azure v1
chat-completions API, JSON mode, streaming, and `max_completion_tokens`, such as
a suitable GPT-4.1 deployment. A Foundry project URL is not the resource endpoint.
API-key authentication is currently supported; managed identity is not.

```powershell
.\.venv\Scripts\nanda-workbench.exe --port 8766
```

Open **http://127.0.0.1:8766/**. On macOS/Linux, run `nanda-workbench --port 8766`
from the activated environment. Configuration is reread from `.env` when you
recheck settings or start a run; a restart is not necessary.

### Using an existing coco installation

coco is optional and separately distributed; it is not bundled with this public
project. Use it only where your organization's access and usage rules permit.
Install and authenticate it using your authorized distribution's instructions,
then verify `coco status`, `coco doctor`, and `coco models`. Claude Code must support
`--bare`, tool disabling, single-turn limits, and streaming JSON output.
The tested local versions are coco 0.2.8 and Claude Code 2.1.317.

Set these in a local, ignored environment file (for example `.env.coco`):

```dotenv
WORKBENCH_PROVIDER=coco
COCO_MODEL=claude-haiku-4-5
COCO_EXECUTABLE=
```

Use an exact model ID from `coco models`. Leave `COCO_EXECUTABLE` empty if coco
is on PATH or in its standard Windows installation location; otherwise set its
full executable path.

```powershell
.\.venv\Scripts\nanda-workbench.exe --env-file .env.coco --port 8766
```

The workbench invokes `coco run` per model step, with prompts over stdin,
tools and MCP servers disabled, `--bare`, one turn, and session persistence
disabled. It runs outside the repository in a dedicated state subdirectory,
streams text into the same activity UI, validates final JSON, and records
reported token usage. It does not read coco token files, install coco, enable
IDE routing, or change global Claude settings. Existing coco daemons are reused.
Model JSON may be raw or enclosed in exactly one Markdown JSON fence; surrounding
prose and wrong schemas remain errors. The unmodified text stays in live evidence.
Text is displayed when the CLI provides it; some models buffer an entire response
rather than emitting fine-grained text deltas.

This is **cloud inference through Copilot**, not a local model and not guaranteed
free usage. Account entitlements, quota, and organizational policies apply.
All coco roles share the dependency `copilot-via-coco`: different model names do
not demonstrate independent resources. Pausing that dependency makes subsequent
steps fail explicitly; there is no automatic Azure fallback. Select
`WORKBENCH_PROVIDER=azure` to return to the existing Azure configuration.

### Workflows

- **Research:** provide a question and up to four supported public URLs. Reader
  agents extract evidence, a writer produces a cited brief, and a reviewer checks
  it. Exact quotations must occur in the retrieved text, and inline source IDs
  must match the declared sources. These checks do **not** prove that a claim
  follows from its citation. Save edits separately from the original output.
- **Evaluations:** provide a task, reference policy, and rubric. A target produces
  a baseline answer; a challenger generates one to three test cases; the target
  answers each; a judge labels each response with quoted evidence. The target
  is the configured provider model, not an arbitrary external production agent.
  Judges can be wrong and share model biases; labels are not ground truth.
- **Activity and history:** streamed output is separated by step and attempt.
  Completed, failed, and cancelled runs retain local evidence. Export JSON to
  inspect model responses and Nanda Town events; download edited brief text.
- **Resources:** inspect shared Azure hosts and pause new calls locally. Configure
  `AZURE_OPENAI_BACKUP_ENDPOINT`, `AZURE_OPENAI_BACKUP_API_KEY`, and
  `AZURE_OPENAI_BACKUP_DEPLOYMENT` for a second resource. Two deployments on the
  **same host** are one dependency, not independent failover. Even distinct Azure
  resources still share a cloud provider.

Without retries, research uses one model call per unique source plus two;
evaluation uses two plus two per test case. Each run has a hard limit of **12
model-step invocations**, an output limit of 2,200 tokens requested from the
provider/CLI, and a 90-second Azure or 120-second coco deadline per invocation.
CLI/provider-internal retries can add underlying requests; the step limit is
not a guarantee about billing. At most two runs can be active. A consent checkbox is required.
Reported token counts cover completed responses, not all potentially billable
failed or cancelled calls; they are not a price estimate.

### How the live application uses Nanda Town

Six role-specific local agents per deployment (reader, writer, reviewer,
challenger, target, judge) register with the upstream owned registry. The
orchestrator discovers candidates through `TownAPI.lookup`, selects one using
the benchmark's shared policy function, sends a signed work envelope through
Nanda Town, awaits Azure HTTPS or coco CLI, and sends a signed result back. These are fixed,
inspectable workflows, not independently deployed autonomous agents.

`workbench.local.v1` delivers local envelopes synchronously through upstream
authorization; `workbench.selection.v1` tracks reservations and retries.
Selection state is shared within a run, not between different runs. The
workbench's primary/backup routing priorities are **not monetary prices**.
Live JSON exports are application journals, not the benchmark's signed,
replay-verifiable Lab evidence bundles.

To explore a shared failure, start a task, open **Agents & resources**, pause the
primary host, then inspect subsequent attempts. Calls already submitted continue.
This injects a local gateway failure; it does not disable the provider. With only one
host, recovery is impossible and the task fails explicitly. Repeating live tasks
with different selection policies is not a controlled statistical comparison:
model responses, timing, and provider conditions vary. Use the paired-seed
benchmark below for quantitative policy claims.

### Privacy, scope, and tests

The server binds only to localhost. It has no user accounts and is **not** an
authenticated public hosting solution; do not expose it through a public tunnel.
Use only provider accounts and material you have permission to use.

Prompts and public source text go to the configured cloud provider.
History, events, and drafts are stored in `.workbench/runs.sqlite3`.
If the checkout is inside a cloud-synced folder, that database may also sync.
Use `--state-dir` pointing outside such folders when appropriate. Exports contain
prompts and outputs; review them before sharing. API keys are not recorded in
status responses or model evidence.

Supported source hosts are listed by `/api/status` and enforced on every redirect.
Only public HTTPS HTML/text is supported, not PDFs, private pages, arbitrary web
search, or browser automation. Downloads are limited to 1 MB, and extracted text
to 10,000 characters per source. A source may reject retrieval or require
JavaScript; the application reports the failure instead of inventing content.

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests\test_workbench.py tests\test_coco.py
```

Tests use explicitly labeled HTTP/subprocess fixtures for reproducibility and
never spend Azure credits or Copilot quota. The application itself has no
mock-response mode. Passing these tests does not verify provider credentials,
deployment support, or live quality.

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

Python 3.11 or 3.12 and Git are required. The benchmark and automated tests need
no model credentials or API spending. The live workbench requires Azure access
or an authorized coco installation and may incur cloud charges or consume Copilot quota.

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
