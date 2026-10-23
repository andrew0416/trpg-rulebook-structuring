"""
refs 실험: 재주(feat)의 '전제조건' 문자열을 그래프 간선으로 해소한다.
PTK 는 SRD 식 교차참조 ((see "X")) 가 없고, 대신 전제조건 문자열이 사실상의 의존 그래프다.

입력: output/entities/feat.json, classes.json, edge.json
출력: output/feat-graph.json, output/feat-graph.md
"""
import json
import os
import re
import sys
from collections import Counter

SKILLS = ["곡예", "육상", "전투", "협박", "은신", "생존", "일반 지식", "의학", "오컬트학", "포켓몬학", "기술학", "교활", "통찰", "매력", "명령", "집중", "직감", "일반지식"]
RANKS = ["불능", "미숙", "초보", "숙련", "전문", "달인", "거장"]
SKILL_RE = re.compile(r"(" + "|".join(RANKS) + r")\s*(?:랭크(?:의)?\s*)?(" + "|".join(sorted(SKILLS, key=len, reverse=True)) + r")?")
LEVEL_RE = re.compile(r"레벨\s*(\d+)")
RANK_TAG_RE = re.compile(r"\s*랭크\s*(\d+)$")
SPLIT_RE = re.compile(r"\s*(?:,|;|/|\s또는\s|\s혹은\s|\s및\s|\s그리고\s)\s*")


def norm(s):
    s = re.sub(r"[‘’'\"“”]", "", s)
    s = re.sub(r"\(.*?\)", "", s)
    return re.sub(r"\s+", " ", s).strip(" .")


def main(ent_dir, out_dir):
    feats = json.load(open(os.path.join(ent_dir, "feat.json"), encoding="utf-8"))
    classes = json.load(open(os.path.join(ent_dir, "classes.json"), encoding="utf-8"))
    edges = json.load(open(os.path.join(ent_dir, "edge.json"), encoding="utf-8"))
    names = {}
    for f in feats:
        names.setdefault(norm(f["name"]), f["id"])
    for c in classes:
        names.setdefault(norm(c["name"]), c["id"])
        names.setdefault(norm(c["name"]) + " 재주", c["id"])
    for e in edges:
        names.setdefault(norm(e["name"]), e["id"])
    # 서플리먼트 클래스는 h2 라 classes.json 에 없다 → 재주 목록 헤딩(list:feat 노드)의 제목을 클래스 노드로 등록
    smap = json.load(open(os.path.join(os.path.dirname(ent_dir.rstrip("/\\")), "structure-map.json"), encoding="utf-8"))
    for n in smap["nodes"]:
        if n["unit_type"] == "list:feat":
            title = norm(re.sub(r"\(.*?\)|\[img\]", "", n["title"]))
            cid = "class/" + re.sub(r"\s+", "-", title)
            for alias in {title, title.split(":")[-1].strip()}:       # '강철 원소술사: 스틸하트' → '스틸하트' 도 등록
                names.setdefault(alias, cid)
                names.setdefault(alias + " 재주", cid)
    kinds = Counter()
    nodes, links, unresolved = [], [], []
    for f in feats:
        pre = norm(f.get("prereq") or "")
        refs = []
        if not pre or pre in ("없음", "-", "없음."):
            kinds["none"] += 1
        elif pre.startswith("GM"):
            kinds["gm_permission"] += 1
            refs.append({"kind": "gm_permission"})
        else:
            last_rank = None
            for tok in SPLIT_RE.split(pre):
                tok = norm(tok)
                if not tok:
                    continue
                tok = RANK_TAG_RE.sub("", tok)
                tok = re.sub(r"\s*중\s*(?:하나|한\s*개)$", "", tok)
                m = LEVEL_RE.search(tok) or re.search(r"(\d+)\s*레벨", tok)
                if m:
                    refs.append({"kind": "level", "min": int(m.group(1))}); kinds["level"] += 1; continue
                m = SKILL_RE.search(tok)
                if m and m.group(2):
                    last_rank = m.group(1)
                    refs.append({"kind": "skill_rank", "skill": m.group(2), "rank": m.group(1)}); kinds["skill_rank"] += 1; continue
                if tok in SKILLS and last_rank:        # '숙련 집중, 교활, 또는 통찰' 의 뒤쪽 토큰
                    refs.append({"kind": "skill_rank", "skill": tok, "rank": last_rank, "rank_inherited": True}); kinds["skill_rank"] += 1; continue
                if m and m.group(1) and ("스킬" in tok or "랭크" in tok):
                    refs.append({"kind": "skill_rank_any", "rank": m.group(1), "text": tok}); kinds["skill_rank_any"] += 1; continue
                m2 = re.match(r"^(.+?) 재주 (\d+)개$", tok)
                if m2 and norm(m2.group(1)) in names:
                    refs.append({"kind": "feat_count", "ref": names[norm(m2.group(1))], "count": int(m2.group(2))}); kinds["feat_count"] += 1; continue
                if tok in names:
                    refs.append({"kind": "feat", "ref": names[tok]}); kinds["feat"] += 1; continue
                if tok.startswith("마이너 기프트") or tok.startswith("메이저 기프트") or "기프트" in tok:
                    refs.append({"kind": "gift", "text": tok}); kinds["gift"] += 1; continue
                refs.append({"kind": "unresolved", "text": tok}); kinds["unresolved"] += 1
                unresolved.append(tok)
        nodes.append({"id": f["id"], "name": f["name"], "chapter": f["chapter"], "prereq": f.get("prereq"), "refs": refs})
        for r in refs:
            if r.get("ref"):
                links.append({"from": f["id"], "to": r["ref"], "kind": r["kind"]})
    json.dump({"nodes": nodes, "links": links}, open(os.path.join(out_dir, "feat-graph.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    tot = sum(kinds.values())
    resolved = tot - kinds["unresolved"]
    in_deg = Counter(l["to"] for l in links)
    lines = ["# 재주 전제조건 → refs 그래프 (자동 생성)", "",
             f"재주 {len(feats)}개, 전제조건 토큰 {tot}개 중 해소 {resolved}개 ({resolved/tot:.0%}), 간선(재주/클래스/엣지 참조) {len(links)}개.", "",
             "| 토큰 종류 | 수 |", "|---|---|"]
    for k, v in kinds.most_common():
        lines.append(f"| {k} | {v} |")
    lines += ["", "## 가장 많이 참조되는 노드", "", "| 노드 | 들어오는 간선 |", "|---|---|"]
    for k, v in in_deg.most_common(15):
        lines.append(f"| {k} | {v} |")
    uc = Counter(unresolved)
    lines += ["", f"## 미해소 토큰 상위 ({len(uc)}종)", "", ", ".join(f"{k}({v})" for k, v in uc.most_common(40))]
    open(os.path.join(out_dir, "feat-graph.md"), "w", encoding="utf-8").write("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
