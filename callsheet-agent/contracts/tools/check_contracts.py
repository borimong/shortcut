"""계약 점검 도구.

    pip install -r contracts/tools/requirements.txt
    python contracts/tools/check_contracts.py                       # 1) 계약 파일 자체 점검 (PR마다)
    python contracts/tools/check_contracts.py --backend http://localhost:8080   # 2) backend가 계약대로 응답하는지
    python contracts/tools/check_contracts.py --mcp http://localhost:9101/mcp --mcp http://localhost:9102/mcp
                                                                    # 3) MCP 서버 도구가 mcp-tools.json과 같은지

1) 스키마 문법, OpenAPI의 $ref가 전부 실제로 있는지, operationId 중복, 예제가 스키마에 맞는지
2) /internal/** 응답과 오류 본문이 스키마에 맞는지, 승인 없는 확정이 409로, 위반안 저장이 422로 막히는지
   (확정·예약은 하지 않는다. 변경안 저장은 1건 생긴다. mock-backend와 실제 backend 모두에 쓸 수 있다)
3) 도구 이름, 필수 인자, destructiveHint가 계약과 같은지 (fastmcp 필요)
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

import yaml
from jsonschema import Draft202012Validator, FormatChecker
from jsonschema.exceptions import best_match
from referencing import Registry, Resource

ROOT = Path(__file__).resolve().parents[1]
BASE = "https://callsheet.local/schemas/"
FAILS: list[str] = []


def ok(msg: str) -> None:
    print(f"  ok   {msg}")


def fail(msg: str) -> None:
    FAILS.append(msg)
    print(f"  FAIL {msg}")


# ---------------------------------------------------------------- 스키마


def load_registry() -> Registry:
    resources = []
    for p in sorted((ROOT / "schemas").glob("*.json")):
        doc = json.loads(p.read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(doc)
        if doc.get("$id") != BASE + p.name:
            fail(f"{p.name}: $id가 {BASE + p.name}이어야 한다")
        resources.append((doc["$id"], Resource.from_contents(doc)))
    return Registry().with_resources(resources)


REGISTRY: Registry | None = None


def validator(ref: str) -> Draft202012Validator:
    """ref 예: 'task.schema.json#/$defs/QueueMessage'"""
    return Draft202012Validator({"$ref": BASE + ref}, registry=REGISTRY, format_checker=FormatChecker())



def _deepest(e):
    """oneOf 오류면 type/event 값이 맞는 갈래를 골라 그 안의 오류를 보여준다."""
    while e.context:
        branches: dict = {}
        for sub in e.context:
            branches.setdefault(sub.relative_schema_path[0], []).append(sub)
        matching = [errs for errs in branches.values() if not any(x.validator == "const" for x in errs)]
        pool = matching[0] if matching else e.context
        e = best_match(pool)
    return e


def check_instance(ref: str, instance, label: str) -> bool:
    e = best_match(validator(ref).iter_errors(instance))
    if e is not None:
        e = _deepest(e)
        fail(f"{label}: {ref} 위반 — {'/'.join(map(str, e.absolute_path)) or '(root)'}: {e.message[:160]}")
        return False
    ok(f"{label} ⟶ {ref.split('/')[-1]}")
    return True


# ---------------------------------------------------------------- OpenAPI


def resolve_pointer(doc, pointer: str):
    node = doc
    for part in [p for p in pointer.lstrip("/").split("/") if p]:
        part = part.replace("~1", "/").replace("~0", "~")
        node = node[part]
    return node


def walk_refs(node, found: list[str]) -> None:
    if isinstance(node, dict):
        if "$ref" in node and isinstance(node["$ref"], str):
            found.append(node["$ref"])
        for v in node.values():
            walk_refs(v, found)
    elif isinstance(node, list):
        for v in node:
            walk_refs(v, found)


def check_openapi(op_ids: set[str]) -> None:
    for name in ("openapi-external.yaml", "openapi-internal.yaml"):
        spec = yaml.safe_load((ROOT / name).read_text(encoding="utf-8"))
        if not str(spec.get("openapi", "")).startswith("3.1"):
            fail(f"{name}: openapi 3.1이어야 한다")
        refs: list[str] = []
        walk_refs(spec, refs)
        bad = 0
        for ref in set(refs):
            file_part, _, pointer = ref.partition("#")
            try:
                if file_part:
                    target = json.loads((ROOT / file_part).read_text(encoding="utf-8"))
                else:
                    target = spec
                resolve_pointer(target, pointer)
            except (KeyError, FileNotFoundError, TypeError):
                fail(f"{name}: $ref를 찾을 수 없다 → {ref}")
                bad += 1
        n_ops = 0
        for path, item in spec["paths"].items():
            for method, op in item.items():
                if method not in {"get", "post", "put", "patch", "delete"}:
                    continue
                n_ops += 1
                oid = op.get("operationId")
                if not oid:
                    fail(f"{name} {method.upper()} {path}: operationId 없음")
                elif oid in op_ids:
                    fail(f"{name}: operationId 중복 {oid}")
                op_ids.add(oid)
                if not op.get("responses"):
                    fail(f"{name} {method.upper()} {path}: responses 없음")
        if not bad:
            ok(f"{name}: 경로 {len(spec['paths'])}개, 작업 {n_ops}개, $ref {len(set(refs))}개 모두 해석됨")


def check_examples() -> None:
    for item in json.loads((ROOT / "examples" / "index.json").read_text(encoding="utf-8")):
        body = json.loads((ROOT / "examples" / item["file"]).read_text(encoding="utf-8"))
        check_instance(item["schema"], body, f"examples/{item['file']}")


# ---------------------------------------------------------------- backend 실측


def http(base: str, method: str, path: str, *, params=None, body=None, headers=None):
    url = base.rstrip("/") + path + ("?" + urllib.parse.urlencode(params) if params else "")
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers={"Content-Type": "application/json", **(headers or {})})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            raw = resp.read()
            return resp.status, (json.loads(raw) if raw else None)
    except urllib.error.HTTPError as e:
        raw = e.read()
        return e.code, (json.loads(raw) if raw else None)


def check_backend(base: str, token: str, s: dict) -> None:
    h = {"X-Internal-Token": token, "X-User-Id": "3", "X-User-Role": "PRODUCTION_MANAGER", "X-Project-Id": s["project"], "X-Task-Id": "t_contract_check"}
    arr = lambda ref: {"type": "array", "items": {"$ref": BASE + ref}}  # noqa: E731

    def run(method, path, params=None, body=None, want=200, schema=None, headers=None):
        label = f"{method} {path}"
        try:
            status, data = http(base, method, path, params=params, body=body, headers=headers or h)
        except OSError as e:
            fail(f"{label}: 연결 실패 {e}")
            return None
        wants = want if isinstance(want, tuple) else (want,)
        if status not in wants:
            fail(f"{label}: HTTP {status}, 기대 {want} — {str(data)[:140]}")
            return None
        if isinstance(schema, str):
            check_instance(schema, data, f"{label} [{status}]")
        elif schema is not None:
            errs = list(Draft202012Validator(schema, registry=REGISTRY).iter_errors(data))
            fail(f"{label}: {errs[0].message[:160]}") if errs else ok(f"{label} [{status}]")
        return data

    d, blk = s["date"], s["block"]
    run("GET", f"/internal/ontology/entities/ACTOR/{s['actor']}", schema="domain.schema.json#/$defs/EntityContext")
    run("POST", "/internal/ontology/impact", body={"eventType": "WEATHER", "entityType": "LOCATION", "entityId": s["location"], "date": d},
        schema="domain.schema.json#/$defs/ImpactResult")
    run("GET", f"/internal/plan-sets/{blk}", params={"date": d}, schema="plan.schema.json#/$defs/PlanSet")
    run("GET", "/internal/availability", params={"entityType": "ACTOR", "entityId": s["actor"], "date": d}, schema="domain.schema.json#/$defs/Availability")
    ev = run("POST", "/internal/plans/evaluate", body={"blockId": blk}, schema="plan.schema.json#/$defs/EvaluationResult")
    cand = run("POST", "/internal/plans/build", body={"blockId": blk, "choice": {"location": "P1", "equipment": "P1", "time": "P1"}},
               schema="plan.schema.json#/$defs/PlanCandidate")
    if cand:
        run("POST", "/internal/plans/validate", body={"planHash": cand["planHash"]}, schema="plan.schema.json#/$defs/ValidationResult")
    run("GET", "/internal/external/weather", params={"locationId": s["location"], "date": d}, schema="domain.schema.json#/$defs/Weather")
    run("GET", "/internal/external/route", params={"from": s["location"], "to": s["location2"]}, schema="domain.schema.json#/$defs/Route")
    run("GET", "/internal/external/equipment-quote", params={"packageId": "PKG-LIGHT", "date": d}, schema="domain.schema.json#/$defs/EquipmentQuote")
    run("GET", "/internal/external/locations", schema="domain.schema.json#/$defs/LocationSearchResult")
    nf = run("GET", "/internal/ontology/entities/ACTOR/A9999", want=404, schema="common.schema.json#/$defs/Error")
    if nf is not None and not (nf.get("details") or {}).get("available"):
        fail("ENTITY_NOT_FOUND: details.available이 비어 있다 (모델이 재시도할 정보가 없다)")
    run("POST", "/internal/plans/validate", body={"planHash": "000000000000"}, want=404, schema="common.schema.json#/$defs/Error")
    if ev and ev.get("ranked"):
        saved = run("POST", "/internal/plans", body={"planHash": ev["ranked"][0]["planHash"], "reason": "계약 점검"}, want=201,
                    schema="plan.schema.json#/$defs/SavedPlan")
        if saved:
            e = run("POST", f"/internal/plans/{saved['planId']}/commit", body={"dataVersion": saved["dataVersion"]}, want=409,
                    schema="common.schema.json#/$defs/Error")
            if e and e.get("code") != "APPROVAL_REQUIRED":
                fail("승인 없는 commit의 code가 APPROVAL_REQUIRED여야 한다")
    if cand:
        e = run("POST", "/internal/plans", body={"planHash": cand["planHash"], "reason": "위반안"}, want=422, schema="common.schema.json#/$defs/Error")
        if e and not (e.get("details") or {}).get("violations"):
            fail("HARD_VIOLATION: details.violations가 비어 있다")
    if run("GET", f"/internal/plan-sets/{blk}", params={"date": d}, want=401, headers={**h, "X-Internal-Token": "wrong"}) is not None:
        ok("잘못된 X-Internal-Token → 401")
    event = json.loads((ROOT / "examples" / "event-evaluation.json").read_text(encoding="utf-8"))
    if run("POST", "/internal/tasks/t_contract_check/events", body=event, want=(202, 404), headers={"X-Internal-Token": token}) is not None:
        ok("POST /internal/tasks/{taskId}/events")


# ---------------------------------------------------------------- MCP 실측


def check_mcp(urls: list[str]) -> None:
    import anyio

    try:
        from fastmcp import Client
    except ImportError:
        fail("--mcp 점검에는 fastmcp가 필요하다 (pip install fastmcp)")
        return
    contract = json.loads((ROOT / "mcp-tools.json").read_text(encoding="utf-8"))
    expected = {t["name"]: t for srv in contract["servers"].values() for t in srv["tools"]}

    async def run() -> None:
        for url in urls:
            async with Client(url) as c:
                tools = await c.list_tools()
            for t in tools:
                exp = expected.get(t.name)
                if not exp:
                    fail(f"{url}: 계약에 없는 도구 {t.name}")
                    continue
                schema = getattr(t, "input_schema", None) or getattr(t, "inputSchema", {})
                req, exp_req = set(schema.get("required", [])), set(exp["inputSchema"].get("required", []))
                destructive = bool(getattr(t.annotations, "destructive_hint", None) or getattr(t.annotations, "destructiveHint", None))
                if req != exp_req:
                    fail(f"{t.name}: 필수 인자 {sorted(req)} ≠ 계약 {sorted(exp_req)}")
                elif destructive != bool(exp["annotations"]["destructiveHint"]):
                    fail(f"{t.name}: destructiveHint가 계약과 다르다")
                else:
                    ok(f"{url} {t.name}")

    anyio.run(run)


# ---------------------------------------------------------------- main


def main() -> int:
    global REGISTRY
    ap = argparse.ArgumentParser()
    ap.add_argument("--backend", help="backend 주소. 예: http://localhost:8080")
    ap.add_argument("--token", default="dev-internal-token")
    ap.add_argument("--mcp", action="append", default=[], help="MCP 주소. 여러 번 줄 수 있다")
    ap.add_argument("--project", default="drama-ep07")
    ap.add_argument("--block", default="B2")
    ap.add_argument("--location", default="L01")
    ap.add_argument("--location2", default="L02")
    ap.add_argument("--actor", default="A04")
    ap.add_argument("--date", default="2026-11-12")
    args = ap.parse_args()

    print("[1] 스키마")
    REGISTRY = load_registry()
    ok(f"schemas/*.json {len(list((ROOT / 'schemas').glob('*.json')))}개 문법 정상")
    print("[2] OpenAPI")
    check_openapi(set())
    print("[3] 예제")
    check_examples()
    if args.backend:
        print(f"[4] backend 실측: {args.backend}")
        check_backend(args.backend, args.token, {"project": args.project, "block": args.block, "location": args.location,
                                                  "location2": args.location2, "actor": args.actor, "date": args.date})
    if args.mcp:
        print("[5] MCP 실측")
        check_mcp(args.mcp)

    print(f"\n{'통과' if not FAILS else f'실패 {len(FAILS)}건'}")
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
