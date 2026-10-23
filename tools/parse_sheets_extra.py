"""
데이터베이스 시트의 나머지 탭을 엔티티로 구조화한다. CSV는 import_source_xlsx.py로 원본 행/열과 혼합 자료형을 보존한다.
  learnsets.csv       포켓몬 데이터2: 0 이름, 1 자력기(레벨업), 2 기술머신, 3 교배기, 4 가르침기술, 5 진화 정보, 6 특성, 7 키, 8 무게, 9 식성, 10 서식지, 11 알 부화시간, 12 기타
  pokemon-skills.csv  포켓몬 스킬: 종별 스킬 랭크 17종(+수정치)
  inventory.csv       인벤 데이터: 아이템 6개 열 묶음(중요 도구/약/음식/포켓몬 도구/몬스터볼/장비품)
  item-data.csv       아이템 데이터: 0/1 음식, 2/3 소지 도구(메가스톤 등), 4/5 재능(중복), 6/7 날씨·필드
  class-data.csv      클래스 데이터: 행0 그룹 라벨, 행1 열 이름; 열 0-2 클래스 메커닉, 3-6 레시피/케이스, 7-10 테크닉, 11-15 전설 기프트
  pokebot.csv         포켓봇 데이터: 조회 표
출력: output/entities/*.json, output/sheets-extra-coverage.md
"""
import csv
import json
import os
import re
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from source_locations import record as source_record
from collections import Counter

csv.field_size_limit(10**8)
MOVE_TOK = re.compile(r"(\d+)\s+([^\s\-–]+(?:\s+[^\s\-–]+)*?)\s*[-–]\s*([가-힣]+)")


def slug(s):
    s = re.sub(r"\[.*?\]|\(.*?\)", "", str(s))
    return re.sub(r"[^0-9a-z가-힣]+", "-", s.lower()).strip("-") or "x"


def rows_of(path):
    return list(csv.reader(open(path, encoding="utf-8", newline="")))


def parse_levelup(cell):
    return [{"level": int(l), "move": m.strip(), "type": t} for l, m, t in MOVE_TOK.findall(cell)]


def parse_list(cell, strip_label=""):
    cell = cell.replace(strip_label, "").replace("\r", "").replace("\n", " ")
    return [x.strip() for x in cell.split(",") if x.strip()]


def parse_abilities(cell):
    out = {}
    for m in re.finditer(r"(기본 특성|숨겨진 특성|대단한 특성)\s*(\d*)\s*[:：]\s*([^\r\n]+)", cell):
        out.setdefault(m.group(1), []).append(m.group(3).strip())
    return out


def learnsets(db):
    rows = rows_of(os.path.join(db, "learnsets.csv"))
    recs = []
    header = next((i for i,r in enumerate(rows) if r and "포켓몬 이름" in r[0]),0)
    for row_number,r in enumerate(rows[header+1:],header+2):
        if not r or not r[0].strip():
            continue
        g = lambda i: r[i] if i < len(r) else ""
        hm = re.search(r"([\d.]+)\s*m\s*\(([^)]+)\)", g(7))
        wm = re.search(r"([\d.]+)\s*kg\s*\((\d+)\)", g(8))
        recs.append({"id": "learnset/" + slug(g(0)), "species": g(0).strip(), "confidence": "auto",
                     "level_up": parse_levelup(g(1)), "tm": parse_list(g(2), "기술머신"), "egg": parse_list(g(3)), "tutor": parse_list(g(4), "가르침기술"),
                     "evolution": [x.strip() for x in g(5).replace("\r", "").split("\n") if x.strip()],
                     "abilities": parse_abilities(g(6)),
                     "height_m": float(hm.group(1)) if hm else None, "size": hm.group(2) if hm else g(7).strip(),
                     "weight_kg": float(wm.group(1)) if wm else None, "weight_class": int(wm.group(2)) if wm else None,
                     "diet": g(9).strip(), "habitat": g(10).strip(), "hatch": g(11).strip(), "note": g(12).strip(), "_source": source_record("learnsets.csv",row_number,{"name":1,"level_up":2,"tm":3,"egg":4,"tutor":5,"evolution":6,"abilities":7})})
    stats = {"rows": len(recs), "level_up_moves_total": sum(len(x["level_up"]) for x in recs),
             "with_tm": sum(1 for x in recs if x["tm"]), "with_egg": sum(1 for x in recs if x["egg"]), "with_abilities": sum(1 for x in recs if x["abilities"])}
    return recs, stats


def species_skills(db):
    rows = rows_of(os.path.join(db, "pokemon-skills.csv"))
    hdr = rows[0]
    recs = []
    for row_number,r in enumerate(rows[1:],2):
        if not r or not r[0].strip():
            continue
        sk = {}
        for i in range(1, len(hdr) - 1, 2):
            if i < len(r) and r[i].strip():
                sk[hdr[i]] = {"rank": int(r[i]) if r[i].strip().isdigit() else r[i], "mod": r[i + 1] if i + 1 < len(r) else ""}
        recs.append({"id": "species-skills/" + slug(r[0]), "species": r[0].strip(), "skills": sk, "_source": source_record("pokemon-skills.csv",row_number,{"name":1})})
    return recs


def items_sheet(db):
    rows = rows_of(os.path.join(db, "inventory.csv"))
    groups = [(0, "중요한 도구", ["name", "price", "desc"]), (3, "약", ["name", "price", "desc"]), (6, "음식", ["name", "price", "desc"]),
              (9, "포켓몬 도구", ["name", "price", "desc"]), (12, "몬스터볼", ["name", "price", "mod", "desc"]), (16, "장비품", ["name", "price", "slot", "desc"])]
    recs, cur = [], {}
    header = next(i for i,r in enumerate(rows) if r and r[0] == "이름") if any(r and r[0] == "이름" for r in rows) else 0
    for row_number,r in enumerate(rows[header+1:],header+2):
        for col, cat, fields in groups:
            vals = [r[col + k].strip() if col + k < len(r) else "" for k in range(len(fields))]
            if not vals[0]:
                continue
            if not vals[1] and not vals[-1]:
                cur[cat] = vals[0]
                continue
            rec = {"id": f"item/{slug(vals[0])}", "name": vals[0], "category": cat, "subcategory": cur.get(cat)}
            for f, v in zip(fields[1:], vals[1:]):
                rec[f] = v
            m = re.search(r"(\d[\d,]*)", rec.get("price", ""))
            rec["_source"] = source_record("inventory.csv",row_number,{field:col+i+1 for i,field in enumerate(fields)})
            rec["price_num"] = int(m.group(1).replace(",", "")) if m else None
            recs.append(rec)
    # item-data (headers=1): 열 0/1 음식, 2/3 소지 도구, 4/5 재능(중복) 뒤에 증강(이름/슬롯/개수/설명)이 이어짐,
    # 열 7 날씨·필드 효과 12개 (이름은 원래 헤더 셀에만 있어 순서로 복원)
    FIELD_NAMES = ["싸라기눈", "비바라기", "모래바람", "쾌청", "일렉트릭필드", "미스트필드", "사이코필드", "그래스필드", "트릭룸", "원더룸", "중력", "매직룸"]
    rows2 = rows_of(os.path.join(db, "item-data.csv"))
    held, fields, augments = [], [], []
    seen = {x["name"] for x in recs}
    for row_number,r in enumerate(rows2[1:],2):
        g = lambda i: r[i].strip() if i < len(r) else ""
        if g(2) and g(2) not in seen:
            held.append({"id": f"item/{slug(g(2))}", "name": g(2), "category": "소지 도구", "desc": g(3), "_source": source_record("item-data.csv",row_number,{"name":3,"desc":4})})
            seen.add(g(2))
        if g(0) and g(0) not in seen:
            held.append({"id": f"item/{slug(g(0))}", "name": g(0), "category": "음식", "desc": g(1), "_source": source_record("item-data.csv",row_number,{"name":1,"desc":2})})
            seen.add(g(0))
        if g(6).isdigit() and g(4):
            augments.append({"id": f"augment/{slug(g(4))}", "name": g(4), "slot": g(5), "slots": int(g(6)), "desc": g(7), "_source": source_record("item-data.csv",row_number,{"name":5,"slot":6,"slots":7,"desc":8})})
        elif g(7) and g(6) in FIELD_NAMES:
            fields.append({"id": f"field/{slug(g(6))}", "name": g(6), "text": g(7), "_source": source_record("item-data.csv",row_number,{"name":7,"text":8})})
        elif g(7) and not g(6) and len(fields) < len(FIELD_NAMES):
            fields.append({"id": f"field/{slug(FIELD_NAMES[len(fields)])}", "name": FIELD_NAMES[len(fields)], "text": g(7), "_source": source_record("item-data.csv",row_number,{"text":8})})
    held += [{"id": a["id"], "name": a["name"], "category": "증강(사이버네틱)", "desc": a["desc"], "slot": a["slot"], "slots": a["slots"], "_source": a["_source"]} for a in augments]
    return recs, held, fields


def class_sheet(db):
    rows = rows_of(os.path.join(db, "class-data.csv"))
    mech, recipes, techniques, gifts = [], [], [], []
    for row_number,r in enumerate(rows[2:],3):
        g = lambda i: r[i].strip() if i < len(r) else ""
        if g(0):
            mech.append({"id": f"class-mechanic/{slug(g(0))}", "class": g(0), "mechanic": g(1), "text": g(2), "_source": source_record("class-data.csv",row_number,{"class":1,"mechanic":2,"text":3})})
        elif g(2) and mech:
            mech[-1]["text"] += "\n" + g(2)
            mech[-1]["_source"]["record_span"][1] = row_number
        if g(3):
            recipes.append({"id": f"recipe/{slug(g(3))}", "name": g(3), "prereq": g(4), "cost": g(5), "effect": g(6), "kind": "케이스" if "케이스" in g(3) else "레시피", "_source": source_record("class-data.csv",row_number,{"name":4,"prereq":5,"cost":6,"effect":7})})
        if g(7):
            techniques.append({"id": f"technique/{slug(g(7))}", "name": g(7), "kind": g(8), "frequency_cost": g(9), "effect": g(10), "_source": source_record("class-data.csv",row_number,{"name":8,"kind":9,"frequency_cost":10,"effect":11})})
        elif g(10) and techniques:
            techniques[-1]["effect"] += "\n" + g(10)
            techniques[-1]["_source"]["record_span"][1] = row_number
        if g(11):
            gifts.append({"id": f"gift/{slug(g(11))}", "name": g(11), "patron": g(12), "prereq": g(13), "frequency": g(14), "effect": g(15), "_source": source_record("class-data.csv",row_number,{"name":12,"patron":13,"prereq":14,"frequency":15,"effect":16})})
    return mech, recipes, techniques, gifts


def pokebot(db):
    rows = rows_of(os.path.join(db, "pokebot.csv"))
    return [dict(zip(rows[0], r), _source=source_record("pokebot.csv",i,{"name":1})) for i,r in enumerate(rows[1:],2) if r and r[0].strip()]


def dump(ent, name, obj):
    json.dump(obj, open(os.path.join(ent, name), "w", encoding="utf-8"), ensure_ascii=False, indent=1)


def main(root):
    db = os.path.join(root, "input", "db")
    ent = os.path.join(root, "output", "entities")
    ls, st = learnsets(db)
    sk = species_skills(db)
    items, held, fields = items_sheet(db)
    mech, recipes, techniques, gifts = class_sheet(db)
    pb = pokebot(db)
    dump(ent, "learnsets.json", ls)
    dump(ent, "species_skills.json", sk)
    dump(ent, "items_sheet.json", items + held)
    dump(ent, "fields_sheet.json", fields)
    dump(ent, "class_mechanics.json", mech)
    dump(ent, "recipes.json", recipes)
    dump(ent, "techniques.json", techniques)
    dump(ent, "legendary_gifts.json", gifts)
    dump(ent, "pokebot.json", pb)
    cat = Counter(i["category"] for i in items + held)
    lines = ["# 데이터베이스 시트 나머지 탭 구조화 (자동 생성)", "", "| 시트 | 결과 | 비고 |", "|---|---|---|",
             f"| 포켓몬 데이터2 (학습 데이터) | 종 {st['rows']}개, 레벨업 기술 {st['level_up_moves_total']}개 | 기술머신 목록 {st['with_tm']}, 교배기 {st['with_egg']}, 특성 {st['with_abilities']}. XLSX 원본 좌표 보존; 제목/열 이름 행은 데이터에서 제외 |",
             f"| 포켓몬 스킬 | 종 {len(sk)}개 × 스킬 17종 | 랭크 + 수정치 |",
             f"| 인벤 데이터 + 아이템 데이터 | 아이템 {len(items) + len(held)}개 | " + ", ".join(f"{k} {v}" for k, v in cat.most_common()) + " |",
             f"| 날씨/필드 정의 | {len(fields)}개 | 아이템 데이터 시트 열 7, 이름은 원본 열 6에서 읽음. 증강(사이버네틱) {sum(1 for x in held if x['category'].startswith('증강'))}개는 아이템으로 |",
             f"| 클래스 데이터 | 클래스 메커닉 {len(mech)}, 레시피·케이스 {len(recipes)}, 테크닉 {len(techniques)}, 전설 기프트 {len(gifts)} | 열 묶음 4개 |",
             f"| 포켓봇 데이터 | {len(pb)}행 | 조회 표 |"]
    open(os.path.join(root, "output", "sheets-extra-coverage.md"), "w", encoding="utf-8").write("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else ".")
