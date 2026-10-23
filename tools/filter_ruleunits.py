"""
룰셋 프로필로 RuleUnit DB 를 걸러낸다.
  python -X utf8 -I tools/filter_ruleunits.py <root> --ruleset core      → output/ruleunits.core.jsonl + output/ruleset-core.md
  python -X utf8 -I tools/filter_ruleunits.py <root> --matrix            → output/ruleset-matrix.md (모든 프로필 요약)
보고서: 유지/제외 단위 수(출처 그룹·변형별), 코어판→변형판 치환 목록, 끊어진 refs(유지된 단위가 제외된 단위를 가리키는 것).
"""
import json
import os
import sys
from collections import Counter

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "engine"))
from ruleset import RuleFilter, classify  # noqa: E402


def filter_db(root, name, write=True):
    rows = [json.loads(l) for l in open(os.path.join(root, "output/ruleunits.jsonl"), encoding="utf-8")]
    rf = RuleFilter.load(root, name)
    kept, excluded, alias = rf.split(rows)
    kept_ids = {u["id"] for u in kept}
    all_ids = {u["id"] for u in rows}
    dangling = Counter()       # 전체 DB 에는 있는데 이 룰셋에서 제외된 단위를 가리키는 refs 만 센다 (원래 없는 대상은 export 의 미해소 refs 몫)
    for u in kept:
        for ref in u.get("refs") or []:
            to = ref.get("to")
            if to and to in all_ids and to not in kept_ids:
                dangling[to] += 1
    by_group_kept = Counter(classify(u)[0] for u in kept)
    by_reason = Counter(why for _, why in excluded)
    if write:
        with open(os.path.join(root, f"output/ruleunits.{name}.jsonl"), "w", encoding="utf-8") as f:
            for u in kept:
                f.write(json.dumps(u, ensure_ascii=False) + "\n")
        lines = [f"# 룰셋 '{name}' 적용 결과 (자동 생성)", "", rf.description, "", rf.summary(), "",
                 f"- 전체 {len(rows)} 단위 → 유지 {len(kept)}, 제외 {len(excluded)}",
                 "- 유지(출처별): " + ", ".join(f"{g} {n}" for g, n in by_group_kept.most_common()),
                 "- 제외(사유별): " + (", ".join(f"{r} {n}" for r, n in by_reason.most_common()) or "없음"),
                 f"- 코어판 → 변형판 치환 {len(alias)}건: " + (", ".join(f"{b} → {v}" for b, v in sorted(alias.items())[:12]) or "없음"),
                 f"- 끊어진 refs (유지된 단위가 제외된 단위를 가리킴): 대상 {len(dangling)}개, {sum(dangling.values())}건" + (" — " + ", ".join(f"{k}({n})" for k, n in dangling.most_common(8)) if dangling else ""), ""]
        if excluded:
            lines += ["## 제외된 단위 (앞 40개)", ""] + [f"- {u['id']} — {why}" for u, why in excluded[:40]]
        open(os.path.join(root, f"output/ruleset-{name}.md"), "w", encoding="utf-8").write("\n".join(lines) + "\n")
    return {"name": name, "total": len(rows), "kept": len(kept), "excluded": len(excluded), "alias": len(alias), "dangling": sum(dangling.values()), "dangling_targets": len(dangling), "by_reason": by_reason}


def matrix(root):
    profiles = json.load(open(os.path.join(root, "data/rulesets.json"), encoding="utf-8"))["rulesets"]
    lines = ["# 룰셋 프로필 요약 (자동 생성)", "", "| 프로필 | 설명 | 유지 | 제외 | 치환 | 끊어진 refs |", "|---|---|---|---|---|---|"]
    for name, p in profiles.items():
        s = filter_db(root, name, write=False)
        lines.append(f"| {name} | {p.get('description', '')[:60]} | {s['kept']} | {s['excluded']} | {s['alias']} | {s['dangling']} |")
    open(os.path.join(root, "output/ruleset-matrix.md"), "w", encoding="utf-8").write("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    root = sys.argv[1] if len(sys.argv) > 1 and not sys.argv[1].startswith("--") else "."
    if "--matrix" in sys.argv:
        matrix(root)
    else:
        name = sys.argv[sys.argv.index("--ruleset") + 1] if "--ruleset" in sys.argv else "core"
        s = filter_db(root, name)
        print(json.dumps({k: v for k, v in s.items() if k != "by_reason"}, ensure_ascii=False))
