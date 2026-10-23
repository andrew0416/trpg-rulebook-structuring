"""DB(ruleunits.jsonl) 의 effect 유형 가운데 data/effect-vocabulary.json 에 없는 것을 등록한다(첫 출현의 필드를 스케치, status 는 엔진 지원 여부에 따라)."""
import json
import os
import sys
from collections import Counter, defaultdict


def main(root):
    sys.path.insert(0, os.path.join(root, "engine"))
    import effects_ext  # noqa  (확장 핸들러 설치)
    from effects import SUPPORTED  # noqa
    vp = os.path.join(root, "data/effect-vocabulary.json")
    vocab = json.load(open(vp, encoding="utf-8"))
    rows = [json.loads(l) for l in open(os.path.join(root, "output/ruleunits.jsonl"), encoding="utf-8")]
    seen, fields, srcs = Counter(), defaultdict(set), defaultdict(set)
    for u in rows:
        m = u.get("mech")
        if not m or u["kind"] not in ("entity:move", "entity:ability", "entity:feat", "entity:item", "entity:edge", "entity:poke_edge"):
            continue
        for e in m["data"].get("effects", []):
            if isinstance(e, dict) and e.get("type"):
                seen[e["type"]] += 1
                fields[e["type"]].update(k for k in e if k != "type")
                srcs[e["type"]].add(u["kind"].split(":")[1])
    added = []
    for t, n in seen.most_common():
        if t in vocab["effects"]:
            continue
        trainer_layer = not (srcs[t] & {"move", "ability"})
        vocab["effects"][t] = {"fields": {k: "…" for k in sorted(fields[t])[:8]}, "status": "engine" if t in SUPPORTED else ("trainer-layer (engine/items.py 소비 또는 서술)" if trainer_layer else "data (llm 초안에서 등장)"), "count": n, "used_by": sorted(srcs[t])}
        added.append((t, n))
    for t in vocab["effects"]:
        vocab["effects"][t]["status"] = ("engine" if t in SUPPORTED else vocab["effects"][t].get("status", "data")) if not str(vocab["effects"][t].get("status", "")).startswith("engine") or t in SUPPORTED else "data"
        vocab["effects"][t]["count"] = seen.get(t, 0)
    json.dump(vocab, open(vp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"어휘 {len(vocab['effects'])}종 (추가 {len(added)}): " + ", ".join(f"{t}({n})" for t, n in added[:40]))


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else ".")
