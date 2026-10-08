"""Run a resumable, source-labeled sample of practice questions through the live agent."""

from __future__ import annotations

import argparse
import asyncio
import json
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from backend.agent.orchestrator import rehearse_example
from backend.knowledge.generate_scenarios import load_patterns
from backend.models import IncidentState, IncidentStatus
from backend.storage import sqlite as storage

DEFAULT_OUTPUT = Path(__file__).resolve().parents[1] / "reports" / "data" / "practice-benchmark-30.jsonl"


def select_cases(count: int = 30) -> list[dict[str, str]]:
    """Choose distinct failure patterns across all domains; never reuse a worked card."""
    if count != 30:
        raise ValueError("This benchmark uses a fixed, auditable 30-pattern plan")
    by_key = {item["state"].get("seedKey"): item for item in storage.list_incidents("examples")}
    by_domain: dict[str, list[int]] = defaultdict(list)
    for index, row in enumerate(load_patterns()):
        by_domain[row["domain"]].append(index)
    selected: list[dict[str, str]] = []
    for domain_number, (domain, indices) in enumerate(by_domain.items()):
        quota = 3 if domain_number < 8 else 2
        preferred = [0, len(indices) // 2, len(indices) - 1][:quota]
        used_patterns: set[int] = set()
        for position in preferred:
            candidate = None
            for offset in range(len(indices)):
                pattern_index = indices[(position + offset) % len(indices)]
                if pattern_index in used_patterns:
                    continue
                for form in range(5):
                    key = f"scenario-{pattern_index * 5 + form + 1:03d}"
                    item = by_key.get(key)
                    if item and item["state"].get("examplePhase") == "seeded":
                        candidate = {"id": item["id"], "seed_key": key, "domain": domain,
                                     "expected_pattern_id": f"PATTERN-{pattern_index + 1:03d}"}
                        used_patterns.add(pattern_index)
                        break
                if candidate:
                    break
            if not candidate:
                raise ValueError(f"Not enough untouched practice cards for {domain}")
            selected.append(candidate)
    if len(selected) != count or len({item["expected_pattern_id"] for item in selected}) != count:
        raise ValueError("Benchmark plan is incomplete or repeats a source pattern")
    return selected


def plan_path(output: Path) -> Path:
    return output.with_suffix(".plan.json")


def load_or_create_plan(output: Path) -> list[dict[str, str]]:
    path = plan_path(output)
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))["cases"]
    selected = select_cases()
    output.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"created_at": datetime.now(timezone.utc).isoformat(),
                                "cases": selected}, ensure_ascii=False, indent=2), encoding="utf-8")
    return selected


def completed_ids(output: Path) -> set[str]:
    if not output.exists():
        return set()
    return {json.loads(line)["id"] for line in output.read_text(encoding="utf-8").splitlines() if line.strip()}


async def run(output: Path = DEFAULT_OUTPUT) -> None:
    storage.init_db()
    plan = load_or_create_plan(output)
    done = completed_ids(output)
    for index, case in enumerate(plan, 1):
        if case["id"] in done:
            continue
        record = storage.get_incident(case["id"])
        if not record:
            raise ValueError(f"Practice card disappeared: {case['id']}")
        phase = record["state"].get("examplePhase")
        if phase == "investigating":
            state = IncidentState.model_validate(record["state"])
            state.examplePhase = "seeded"
            state.status = IncidentStatus.new
            storage.save_state(state)
            storage.append_event(case["id"], "benchmark_interrupted", {"reason": "worker stopped before result was recorded"})
            phase = "seeded"
        if phase not in ("seeded", "awaiting_review"):
            raise ValueError(f"Practice card changed before benchmark: {case['id']} ({phase})")
        started = time.monotonic()
        print(json.dumps({"progress": f"{index}/{len(plan)}", "id": case["id"],
                          "domain": case["domain"], "stage": "running"}), flush=True)
        _, task = await rehearse_example(case["id"])
        await task
        final = storage.get_incident(case["id"])["state"]
        reference = final.get("exampleReference") or {}
        item = {**case, "question": record["message"], "first_diagnosis": final.get("firstDiagnosis"),
                "first_actions": final.get("firstActions"),
                "reference_cause": reference.get("rootCause"),
                "reference_action": reference.get("successfulAction"),
                "qwen": final.get("providerStatus", {}).get("qwen"),
                "qwen_error": final.get("providerStatus", {}).get("qwen_error"),
                "classification": final.get("classification"),
                "matches": [{"id": match["id"], "verification": match.get("verification"),
                             "score": match.get("score")} for match in final.get("raftMatches", [])],
                "elapsed_seconds": round(time.monotonic() - started, 2),
                "finished_at": datetime.now(timezone.utc).isoformat()}
        with output.open("a", encoding="utf-8") as destination:
            destination.write(json.dumps(item, ensure_ascii=False) + "\n")
        print(json.dumps({"progress": f"{index}/{len(plan)}", "id": case["id"],
                          "stage": "done", "qwen": item["qwen"],
                          "elapsed_seconds": item["elapsed_seconds"]}), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--plan", action="store_true")
    args = parser.parse_args()
    storage.init_db()
    if args.plan:
        print(json.dumps(load_or_create_plan(args.output), ensure_ascii=False, indent=2))
    else:
        asyncio.run(run(args.output))
