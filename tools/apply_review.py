"""
의미 검수 결과 반영: 검수자(사람 또는 LLM 검수 에이전트)가 쓴 result_*.jsonl 을 읽어
  - data/review-verdicts.json  : {unit id: {verdict, note, reviewer}}
  - data/moves-reviewed.json / data/abilities-reviewed.json : verdict=fix 인 항목의 교정된 effects (id 로 키, confidence=reviewed)
  - output/review-report.md    : 집계 + 수정 전/후 + unsure 목록
사용: python -X utf8 -I tools/apply_review.py <root> <result dir> [reviewer label]
result 한 줄: {"id", "verdict": ok|fix|unsure, "note", "effects"(fix 일 때)}
"""
import glob
import json
import os
import sys
from collections import Counter


def main(root, result_dir, reviewer="claude-subagent"):
    queue = {}
    for l in open(os.path.join(root, "output/review-queue.jsonl"), encoding="utf-8"):
        x = json.loads(l)
        queue[x["id"]] = x
    # 큐는 검수가 반영될 때마다 줄어들므로, 이전 큐에 있던 id 는 DB(ruleunits.jsonl)에서 원문·현재 effects 를 가져와 받아들인다 (재실행·보고서 재생성용)
    rp_db = os.path.join(root, "output/ruleunits.jsonl")
    if os.path.exists(rp_db):
        for l in open(rp_db, encoding="utf-8"):
            u = json.loads(l)
            if u["id"] in queue or not u.get("mech"):
                continue
            t = u.get("text") or {}
            queue[u["id"]] = {"id": u["id"], "kind": u["kind"], "title": u.get("title", ""), "reason": "(이전 큐)", "text": (t.get("body") if isinstance(t, dict) else str(t)) or "",
                              "effects": (u["mech"].get("data") or {}).get("effects", [])}
    vp = os.path.join(root, "data/review-verdicts.json")
    verdicts = json.load(open(vp, encoding="utf-8")) if os.path.exists(vp) else {}
    mp, ap = os.path.join(root, "data/moves-reviewed.json"), os.path.join(root, "data/abilities-reviewed.json")
    mv = json.load(open(mp, encoding="utf-8")) if os.path.exists(mp) else {"$comment": "의미 검수에서 교정된 기술 effects (id 키). export/engine 은 hand 다음으로 이것을 우선한다.", "moves": {}}
    ab = json.load(open(ap, encoding="utf-8")) if os.path.exists(ap) else {"$comment": "의미 검수에서 교정된 특성 effects (id 키).", "abilities": {}}
    extra_files = {"feats": (os.path.join(root, "data/feats-reviewed.json"), "의미 검수에서 교정된 재주·기프트 effects (id 키). export/engine 은 규칙 기반 full 다음, llm 앞에 둔다."),
                   "items": (os.path.join(root, "data/items-reviewed.json"), "의미 검수에서 교정된 아이템 effects (id 키)."),
                   "edges": (os.path.join(root, "data/edges-reviewed.json"), "의미 검수에서 교정된 엣지·포켓엣지 effects (id 키).")}
    extra = {k: (json.load(open(p, encoding="utf-8")) if os.path.exists(p) else {"$comment": c, k: {}}) for k, (p, c) in extra_files.items()}

    def table_for(uid):
        if uid.startswith("move/"):
            return mv["moves"]
        if uid.startswith("ability/"):
            return ab["abilities"]
        if uid.startswith(("feat/", "gift/")):
            return extra["feats"]["feats"]
        if uid.startswith(("item/", "augment/", "crafted_item/")):
            return extra["items"]["items"]
        if uid.startswith(("edge/", "poke_edge/")):
            return extra["edges"]["edges"]
        return ab["abilities"]
    stats, bad, fixes, unsure = Counter(), [], [], []
    for f in sorted(glob.glob(os.path.join(result_dir, "result_*.jsonl"))):
        for ln, l in enumerate(open(f, encoding="utf-8"), 1):
            l = l.strip()
            if not l:
                continue
            try:
                r = json.loads(l)
            except Exception as ex:
                bad.append(f"{os.path.basename(f)}:{ln} JSON 오류 {ex}")
                continue
            uid = r.get("id")
            if uid not in queue:
                bad.append(f"{os.path.basename(f)}:{ln} 큐에 없는 id {uid}")
                continue
            v = r.get("verdict")
            if v not in ("ok", "fix", "unsure"):
                bad.append(f"{os.path.basename(f)}:{ln} verdict 이상 {v}")
                continue
            if v == "fix":
                eff = r.get("effects")
                if not isinstance(eff, list) or not all(isinstance(e, dict) and e.get("type") for e in eff):
                    bad.append(f"{os.path.basename(f)}:{ln} {uid} fix 인데 effects 가 dict 목록이 아님")
                    continue
                target = table_for(uid)
                target[uid] = {"effects": eff, "note": r.get("note", ""), "reviewer": reviewer}
                fixes.append((uid, queue[uid]["effects"], eff, r.get("note", "")))
            elif v == "unsure":
                unsure.append((uid, r.get("note", "")))
            verdicts[uid] = {"verdict": v, "note": r.get("note", ""), "reviewer": reviewer}
            stats[v] += 1
    json.dump(verdicts, open(vp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    json.dump(mv, open(mp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    json.dump(ab, open(ap, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    for k, (p, _) in extra_files.items():
        json.dump(extra[k], open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    total = sum(stats.values())
    lines = ["# 의미 검수 보고 (자동 생성: tools/apply_review.py)", "",
             f"검수 {total}건 / 큐 {len(queue)}건. ok {stats['ok']} ({100 * stats['ok'] // max(1, total)}%), fix {stats['fix']} ({100 * stats['fix'] // max(1, total)}%), unsure {stats['unsure']} ({100 * stats['unsure'] // max(1, total)}%). 결과 파일 오류 {len(bad)}건.", ""]
    by_reason = Counter()
    by_reason_fix = Counter()
    for uid, v in verdicts.items():
        if uid in queue:
            by_reason[queue[uid]["reason"]] += 1
            if v["verdict"] == "fix":
                by_reason_fix[queue[uid]["reason"]] += 1
    lines += ["| 초안 출처 | 검수 | fix | fix 비율 |", "|---|---|---|---|"]
    for k in sorted(by_reason):
        lines.append(f"| {k} | {by_reason[k]} | {by_reason_fix[k]} | {100 * by_reason_fix[k] // max(1, by_reason[k])}% |")
    if bad:
        lines += ["", "## 결과 파일 오류", ""] + [f"- {b}" for b in bad]
    lines += ["", f"## 교정 {len(fixes)}건 (전 → 후)", ""]
    for uid, before, after, note in fixes:
        lines.append(f"### {uid}\n- 원문: {queue[uid]['text'][:300]}\n- 사유: {note}\n- 전: `{json.dumps(before, ensure_ascii=False)[:400]}`\n- 후: `{json.dumps(after, ensure_ascii=False)[:400]}`\n")
    lines += ["", f"## unsure {len(unsure)}건 (사람 판단 필요)", ""]
    for uid, note in unsure:
        lines.append(f"- {uid}: {note} — 원문: {queue[uid]['text'][:200]}")
    open(os.path.join(root, "output/review-report.md"), "w", encoding="utf-8").write("\n".join(lines) + "\n")
    print("\n".join(lines[:12]))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else "claude-subagent")
