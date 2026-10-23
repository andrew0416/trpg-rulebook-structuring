"""
학습 데이터(종 → 기술/특성 이름)를 기술·특성 DB id 로 해소한다. 표기 변형은 data/name-aliases.json 으로 흡수.
출력: output/entities/learnset_links.json (species → {moves:[ids], abilities:[ids], unresolved}), output/learnset-links.md
"""
import json
import os
import re
import sys
from collections import Counter


def norm(n):
    return re.sub(r"\s+|\*|§|\[.*?\]|\(.*?\)|\r|\n", "", n)


def main(root):
    ent = os.path.join(root, "output", "entities")
    def prefer_core(entities):
        """같은 이름의 코어판과 변형판([홈브류]/[Playtest]/[썬문]/[소실], 동명 -2) 가운데 코어판 id 를 우선한다 (룰셋 필터가 변형판을 끌 수 있으므로)."""
        out = {}
        for x in sorted(entities, key=lambda x: (bool(re.search(r"-(playtest|홈브류|썬문|소실)(-\d+)?$|-\d+$", x["id"])), x["id"])):
            out.setdefault(norm(x["name"]), x["id"])
        return out
    mv = prefer_core(json.load(open(os.path.join(ent, "moves.json"), encoding="utf-8")))
    ab = prefer_core(json.load(open(os.path.join(ent, "abilities.json"), encoding="utf-8")))
    ali_path = os.path.join(root, "data", "name-aliases.json")
    aliases = json.load(open(ali_path, encoding="utf-8")) if os.path.exists(ali_path) else {"moves": {}, "abilities": {}, "not_moves": []}
    not_moves = set(aliases.get("not_moves", []))
    ls = json.load(open(os.path.join(ent, "learnsets.json"), encoding="utf-8"))
    out, um, ua, tot_m, tot_a = [], Counter(), Counter(), 0, 0
    for l in ls:
        moves, abil, unresolved = [], [], []
        names = [(e["move"], "level_up", e["level"]) for e in l["level_up"]]
        for src in ("tm", "egg", "tutor"):
            for x in l[src]:
                n = re.sub(r"^(A?\d+)\s+", "", x).replace("(N)", "").strip()
                names.append((n, src, None))
        for n, src, lv in names:
            tot_m += 1
            key = norm(aliases["moves"].get(n, n))
            if key in mv:
                moves.append({"to": mv[key], "source": src, **({"level": lv} if lv else {})})
            elif n in not_moves or key in {norm(x) for x in not_moves}:
                moves.append({"to": None, "name": n, "source": src, "note": "기술이 아님(키워드 규칙/메모)"})
            else:
                unresolved.append(n)
                um[n] += 1
        for k, v in l["abilities"].items():
            for a in v:
                tot_a += 1
                key = norm(aliases["abilities"].get(a, a))
                if key in ab:
                    abil.append({"to": ab[key], "slot": k})
                else:
                    unresolved.append(a)
                    ua[a] += 1
        out.append({"species": l["species"], "moves": moves, "abilities": abil, "unresolved": unresolved})
    json.dump(out, open(os.path.join(ent, "learnset_links.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    lines = ["# 학습 데이터 → 기술/특성 DB 연결 (자동 생성)", "",
             f"- 기술 참조 {tot_m}개 중 미해소 {sum(um.values())}개 ({sum(um.values())/tot_m:.1%}), 종류 {len(um)}개",
             f"- 특성 참조 {tot_a}개 중 미해소 {sum(ua.values())}개 ({sum(ua.values())/tot_a:.1%}), 종류 {len(ua)}개",
             "", "## 미해소 기술 (상위)", "", ", ".join(f"{k}({v})" for k, v in um.most_common(30)),
             "", "## 미해소 특성 — 특성 시트에 없는 이름 (번역 DB 의 누락)", "", ", ".join(f"{k}({v})" for k, v in ua.most_common(30))]
    open(os.path.join(root, "output", "learnset-links.md"), "w", encoding="utf-8").write("\n".join(lines) + "\n")
    print("\n".join(lines[:4]))


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else ".")
