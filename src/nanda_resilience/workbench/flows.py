from __future__ import annotations

import asyncio
import json
import re

import httpx

from .azure import ProviderError
from .network import LiveNetwork
from .schemas import Answer, Brief, Challenges, Judgment, Review, RunRequest, SourceNotes
from .sources import SourceError, fetch_source


async def research(request: RunRequest, network: LiveNetwork, client: httpx.AsyncClient) -> dict:
    if not request.sources:
        raise SourceError("Add at least one supported public source URL.")
    sources = []
    for index, url in enumerate(dict.fromkeys(request.sources), 1):
        network.emit("source", {"state": "fetching", "url": url})
        source = await fetch_source(client, url, f"S{index}")
        sources.append(source)
        network.emit("source", {"state": "ready", **source})

    async def read(source):
        notes = await network.request(
            "reader", f"Read {source['id']}",
            json.dumps({"question": request.question, "source": source,
                        "instructions": "Extract relevant claims and exact, verbatim quotations."}),
            SourceNotes,
        )
        invalid = [quote for quote in notes["quotes"] if quote not in source["text"]]
        if invalid:
            raise ProviderError("A reader returned a quotation not found in the retrieved source.")
        return {"source_id": source["id"], **notes}

    # TaskGroup cancels sibling requests if any reader fails; no detached work survives a failed run.
    async with asyncio.TaskGroup() as group:
        tasks = [group.create_task(read(source)) for source in sources]
    notes = [task.result() for task in tasks]
    brief = await network.request(
        "writer", "Draft brief",
        json.dumps({"question": request.question, "evidence": notes,
                    "instructions": "Write a useful, specific brief. Cite source IDs as [S1], "
                    "[S2] in the answer and findings. Clearly distinguish inference from evidence."}),
        Brief,
    )
    allowed = {source["id"] for source in sources}
    if not brief["source_ids"] or not set(brief["source_ids"]) <= allowed:
        raise ProviderError("The brief omitted its sources or referred to an unknown source.")
    cited = set(re.findall(r"\[(S\d+)\]", "\n".join([brief["answer"], *brief["findings"]])))
    if not cited or cited != set(brief["source_ids"]):
        raise ProviderError("The brief's inline citations do not match its declared sources.")
    review = await network.request(
        "reviewer", "Review evidence",
        json.dumps({"question": request.question, "brief": brief, "notes": notes,
                    "instructions": "Critique unsupported conclusions and citation gaps. "
                    "You are a model reviewer, not a ground-truth verifier."}), Review,
    )
    return {"kind": "research", "brief": brief, "review": review,
            "sources": sources, "notes": notes}


async def evaluation(request: RunRequest, network: LiveNetwork) -> dict:
    if len(request.rubric.strip()) < 12:
        raise ProviderError("Add a concrete evaluation rubric before running.")
    baseline = await network.request(
        "target", "Baseline response",
        json.dumps({"task": request.question, "reference": request.reference}), Answer,
    )
    challenges = await network.request(
        "challenger", "Design test cases",
        json.dumps({
            "task": request.question, "reference": request.reference,
            "rubric": request.rubric, "count": request.cases,
            "instructions": "Produce exactly count distinct test cases exposing coverage gaps. "
            "Preserve the task's intent; vary ambiguity, boundary conditions, or conflicting "
            "evidence. Each prompt must be self-contained. Do not invent test results.",
        }), Challenges,
    )
    if len(challenges["cases"]) != request.cases:
        raise ProviderError("The challenger did not produce the requested number of test cases.")
    results = []
    for index, case in enumerate(challenges["cases"], 1):
        answer = await network.request(
            "target", f"Run case {index}",
            json.dumps({"task": case["prompt"], "reference": request.reference}), Answer,
        )
        judgment = await network.request(
            "judge", f"Evaluate case {index}",
            json.dumps({
                "task": case["prompt"], "rubric": request.rubric,
                "expected_behavior": case["expected_behavior"],
                "reference": request.reference, "answer": answer["answer"],
                "instructions": "Evaluate only the supplied answer. Evidence_quote must be an "
                "exact substring of the answer, or empty if no supporting quote exists. "
                "Use uncertain where the reference is insufficient. Model judgments are "
                "not established ground truth.",
            }), Judgment,
        )
        if judgment["evidence_quote"] and judgment["evidence_quote"] not in answer["answer"]:
            raise ProviderError("The judge cited evidence not present in the target response.")
        result = {**case, "answer": answer["answer"], "judgment": judgment}
        results.append(result)
        network.emit("case", {"index": index, **result})
    return {"kind": "evaluation", "baseline": baseline["answer"], "cases": results,
            "rubric": request.rubric, "judgment_notice":
                "These are model judgments, not ground-truth labels. Review the evidence yourself."}
