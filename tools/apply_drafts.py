"""
LLM 초안 병합기: 스크래치 폴더의 draft_*.json({"<id>": [effects...]}) 을 모아 data/<kind>-llm.json 으로 저장한다.
  python -X utf8 -I tools/apply_drafts.py <root> feats  <draft_dir>
  python -X utf8 -I tools/apply_drafts.py <root> items  <draft_dir>
  python -X utf8 -I tools/apply_drafts.py <root> edges  <draft_dir>      (edge/ + poke_edge/ 둘 다)
검사: JSON 파싱, id 가 엔티티 표(output/entities/*.json 또는 data/items-mech.json)에 있는지, effect 가 dict 이고 type 이 있는지.
기존 data/<kind>-llm.json 이 있으면 같은 id 는 새 초안으로 덮어쓴다(검수본 data/<kind>-reviewed.json 은 건드리지 않음).
"""
import glob
import json
import os
import sys

KINDS = {
    "feats": {"out": "data/feats-llm.json", "key": "feats", "ids": lambda root: {r["id"] for f in ("feat", "gift", "legendary_gifts") for r in _load(root, f"output/entities/{f}.json") if r.get("id")}},
    "items": {"out": "data/items-llm.json", "key": "items", "ids": lambda root: {k for k in _load(root, "data/items-mech.json") if not k.startswith("$")}
              | {r["id"] for f in ("item", "items_sheet", "crafted_item") for r in _load(root, f"output/entities/{f}.json") if r.get("id")}},
    "edges": {"out": "data/edges-llm.json", "key": "edges", "ids": lambda root: {r["id"] for f in ("edge", "poke_edge") for r in _load(root, f"output/entities/{f}.json")}},
}


def _load(root, rel):
    p = os.path.join(root, rel)
    return json.load(open(p, encoding="utf-8")) if os.path.exists(p) else []


def main(root, kind, src):
    spec = KINDS[kind]
    valid = spec["ids"](root)
    out_path = os.path.join(root, spec["out"])
    merged = _load(root, spec["out"]) or {}
    merged.setdefault("$comment", f"규칙 기반 기계화가 coverage none/partial 로 남긴 {kind} 의 LLM(Claude) mech 초안. confidence=llm, 검수 전. "
                                   "effect 유형은 data/effect-vocabulary.json 어휘(트레이너 계층 포함). 'gm'/'rule' 은 GM 판단·서술 규칙. export 시 auto full > llm > auto partial 순으로 채택.")
    table = merged.setdefault(spec["key"], {})
    n_files = n_new = n_bad = 0
    unknown = []
    for p in sorted(glob.glob(os.path.join(src, "draft_*.json"))):
        d = json.load(open(p, encoding="utf-8"))
        n_files += 1
        for uid, effs in d.items():
            if uid.startswith("$"):
                continue
            if uid not in valid:
                unknown.append(uid); continue
            if not isinstance(effs, list) or not all(isinstance(e, dict) and e.get("type") for e in effs):
                n_bad += 1; print("효과 형식 오류:", uid); continue
            table[uid] = effs
            n_new += 1
    json.dump(merged, open(out_path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"{kind}: 파일 {n_files}개 → {n_new}개 병합 (총 {len(table)}개, 형식 오류 {n_bad}, 미등록 id {len(unknown)}) → {spec['out']}")
    if unknown:
        print("  미등록 id:", ", ".join(unknown[:15]))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], sys.argv[3])
