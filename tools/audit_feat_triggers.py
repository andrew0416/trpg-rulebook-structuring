"""Measure trigger parsing and GM handoff coverage; matching is not semantic proof."""
import json
import sys
from collections import Counter
from pathlib import Path

def main(root):
    root=Path(root)
    sys.path.insert(0,str(root/"engine"))
    from effects import parse_trigger
    rows=[json.loads(x) for x in (root/"output/ruleunits.jsonl").read_text(encoding="utf-8").splitlines()]
    counts=Counter(); out=[]
    for u in rows:
        if u["kind"] not in ("entity:feat","entity:edge","entity:poke_edge") or not u.get("mech"):
            continue
        data=u["mech"]["data"]
        effects=data.get("effects",[])
        trigger=next((e.get("text","") for e in effects if e.get("type")=="trigger"),None)
        trigger=trigger or (data.get("header") or {}).get("trigger") or data.get("trigger")
        if not trigger:
            continue
        parsed=parse_trigger(trigger)
        status="gm-choice" if any(e.get("type")=="gm" for e in effects) else "parsed-candidate" if parsed else "manual"
        counts[status]+=1
        out.append({"id":u["id"],"trigger":trigger,"status":status,"parsed":parsed})
    (root/"output/feat-trigger-audit.json").write_text(json.dumps(out,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    lines=["# 재주 발동조건 점검", "", "집계: "+str(dict(counts)), "", "parsed-candidate는 이벤트 패턴에 매칭됐다는 뜻이며, 모든 조건·대상·빈도가 검증됐다는 뜻은 아니다.", "manual은 기존 수동 발동 경로, gm-choice는 선택·원문 확인을 위해 명시적으로 GM에게 넘기는 경로다.", ""]
    for row in out:
        if row["status"]!="parsed-candidate":
            lines.append(f"- {row['id']} [{row['status']}]: {row['trigger']}")
    (root/"output/feat-trigger-audit.md").write_text("\n".join(lines)+"\n",encoding="utf-8")
    print(lines[2])

if __name__=="__main__":
    main(sys.argv[1] if len(sys.argv)>1 else ".")
