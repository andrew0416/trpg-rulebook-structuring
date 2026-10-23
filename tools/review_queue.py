"""검수 큐: confidence 가 llm / auto+llm 인 단위와 조건 키가 붙은 auto 효과를 원문과 나란히 뽑는다. → output/review-queue.md, output/review-queue.jsonl"""
import json
import os
import sys
from collections import Counter

COND_KEYS = ("if_weather", "on_miss", "duration", "on_ko", "if")


def main(root):
    rows = [json.loads(l) for l in open(os.path.join(root, "output/ruleunits.jsonl"), encoding="utf-8")]
    vp = os.path.join(root, "data/review-verdicts.json")
    verdicts = json.load(open(vp, encoding="utf-8")) if os.path.exists(vp) else {}
    done = Counter()
    q = []
    for u in rows:
        m = u.get("mech")
        if not m or u["kind"] not in ("entity:move", "entity:ability", "entity:feat", "entity:item", "entity:edge", "entity:poke_edge"):
            continue
        effs = m["data"].get("effects", [])
        reason = None
        if m["confidence"] in ("llm", "auto+llm"):
            reason = m["confidence"] + " 초안"
        elif m["confidence"] == "auto" and any(isinstance(e, dict) and any(k in e for k in COND_KEYS) for e in effs):
            reason = "auto + 조건절"
        if m["data"].get("_source_id") and not m["data"].get("_same_source_effect") and m["confidence"] == "auto":
            reason = "동명 변형판 원문별 재검수"
        if m["confidence"] == "reviewed" and verdicts.get(u["id"], {}).get("verdict") != "unsure":
            done["fix 반영"] += 1
            continue
        v = verdicts.get(u["id"], {}).get("verdict")
        if v == "ok" and reason != "동명 변형판 원문별 재검수":
            done["ok"] += 1
            continue
        if v == "unsure":
            reason = (reason or m["confidence"]) + " / 검수 unsure: " + verdicts[u["id"]].get("note", "")
        if reason:
            q.append({"id": u["id"], "kind": u["kind"], "title": u["title"], "reason": reason, "text": u["text"]["body"], "effects": effs})
    with open(os.path.join(root, "output/review-queue.jsonl"), "w", encoding="utf-8") as f:
        for x in q:
            f.write(json.dumps(x, ensure_ascii=False) + "\n")
    lines = ["# 검수 큐 (자동 생성)", "", f"총 {len(q)}건 (검수 완료 제외: " + ", ".join(f"{k} {n}" for k, n in sorted(done.items())) + "): " + ", ".join(f"{r} {n}" for r, n in sorted(Counter(x['reason'].split(' / ')[0] for x in q).items())),
             "", "각 항목: 원문 → 초안 effect. 틀린 것은 data/moves-llm.json / moves-llm-partial.json / abilities-llm.json 에서 고치고 export 를 다시 돌린다.", ""]
    for x in q:
        eff = "; ".join(json.dumps(e, ensure_ascii=False) for e in x["effects"])
        lines.append(f"- **{x['title']}** ({x['id']}, {x['reason']})\n  - 원문: {x['text'][:300].replace(chr(10), ' ')}\n  - 초안: {eff[:600]}")
    open(os.path.join(root, "output/review-queue.md"), "w", encoding="utf-8").write("\n".join(lines) + "\n")
    print(lines[2])


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else ".")
