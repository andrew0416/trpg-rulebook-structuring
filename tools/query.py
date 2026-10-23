"""
DB 조회 도구: output/ruleunits.jsonl 을 id·이름·종류·본문으로 찾아 단위와 mech 를 보여준다.
  python -X utf8 -I tools/query.py <root> 화염방사                  # 이름/id 부분 일치 (기본)
  python -X utf8 -I tools/query.py <root> --kind entity:feat 지시     # 종류 제한
  python -X utf8 -I tools/query.py <root> --text "기회 공격"          # 본문 전문 검색
  python -X utf8 -I tools/query.py <root> --id move/화염방사 --mech   # 정확한 id, mech 전체 출력
  python -X utf8 -I tools/query.py <root> --effect apply_status --status 화상   # effect 유형/필드로 역검색
  python -X utf8 -I tools/query.py <root> --refs feat/엘리트-트레이너 # 이 단위를 참조하는 단위
옵션: --ruleset <name> 으로 output/ruleunits.<name>.jsonl 이 있으면 그 파일을 쓴다. --limit N (기본 20). --json 은 JSON 출력.
"""
import argparse
import json
import os
import sys


def load(root, ruleset=None):
    p = os.path.join(root, f"output/ruleunits.{ruleset}.jsonl" if ruleset else "output/ruleunits.jsonl")
    if not os.path.exists(p):
        p = os.path.join(root, "output/ruleunits.jsonl")
    return [json.loads(l) for l in open(p, encoding="utf-8")]


def body_of(u):
    t = u.get("text") or {}
    if isinstance(t, dict):
        return " ".join(str(v) for v in (t.get("summary"), t.get("body")) if v)
    return str(t)


def match(u, args):
    if args.kind and not u.get("kind", "").startswith(args.kind):
        return False
    if args.id:
        return u["id"] == args.id
    if args.effect or args.status or args.stat:
        effs = ((u.get("mech") or {}).get("data") or {}).get("effects") or []
        for e in effs:
            if not isinstance(e, dict):
                continue
            if args.effect and e.get("type") != args.effect:
                continue
            if args.status and args.status not in str(e.get("status", "")):
                continue
            if args.stat and args.stat != str(e.get("stat", "")):
                continue
            return True
        return False
    if args.refs:
        return any(r.get("to") == args.refs for r in u.get("refs") or [])
    q = (args.query or "").lower()
    if not q:
        return True
    hay = (u["id"] + " " + str(u.get("title", "")) + " " + str((u.get("extra") or {}).get("eng", "")) + (" " + body_of(u) if args.text else "")).lower()
    return q in hay


def fmt(u, mech=False):
    m = u.get("mech") or {}
    line = f"- {u['id']}  [{u.get('kind')}]  {u.get('title', '')}"
    if m:
        line += f"  (mech {m.get('confidence')}/{m.get('coverage')})"
    src = u.get("source") or {}
    if src.get("file"):
        line += f"  ← {src.get('file')}:{(src.get('lines') or [0])[0]}"
    out = [line]
    b = body_of(u).strip().replace("\n", " ")
    if b:
        out.append("    " + b[:300])
    if mech and m:
        out.append("    mech: " + json.dumps(m.get("data"), ensure_ascii=False)[:1500])
    return "\n".join(out)


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("root")
    ap.add_argument("query", nargs="?")
    ap.add_argument("--kind")
    ap.add_argument("--id")
    ap.add_argument("--text", nargs="?", const=True, default=False, help="본문 전문 검색 (값을 주면 그 값이 검색어)")
    ap.add_argument("--effect")
    ap.add_argument("--status")
    ap.add_argument("--stat")
    ap.add_argument("--refs")
    ap.add_argument("--ruleset")
    ap.add_argument("--mech", action="store_true")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--limit", type=int, default=20)
    args = ap.parse_args(argv)
    if isinstance(args.text, str):
        args.query, args.text = args.text, True
    rows = [u for u in load(args.root, args.ruleset) if match(u, args)]
    if args.json:
        print(json.dumps(rows[: args.limit], ensure_ascii=False, indent=1))
        return rows
    print(f"{len(rows)}개 일치" + (f" (앞 {args.limit}개)" if len(rows) > args.limit else ""))
    for u in rows[: args.limit]:
        print(fmt(u, args.mech or bool(args.id)))
    return rows


if __name__ == "__main__":
    main(sys.argv[1:])
