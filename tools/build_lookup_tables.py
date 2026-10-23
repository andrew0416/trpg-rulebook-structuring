"""
D층 실험: 룰북의 조회 표를 lookup_table RuleUnit 으로 자동 변환한다.

- 데미지 표 (ch07 '데미지 표(Damage Charts)')      : 기본 데미지 1~28 -> 굴림 주사위 / 지정 데미지(저/중/고)
- 전투단계 승수 표 (ch07 '전투단계')               : -6..+6 -> 배수
- 스킬 랭크 표 (ch03 '스킬')                       : 랭크 -> d6 개수
- 타입 상성표 (데이터베이스 시트 '성격/타입 정보')  : 룰북 본문에서는 이미지라 추출 불가 -> 시트에서 가져옴
- 성격표 (데이터베이스 시트 '성격/타입 정보')       : 성격 -> 상승/하강 스탯
- 무게 등급표 (ch10 '무게 등급')                  : 1~7등급의 원문 범위·조건

사용법: python -X utf8 -I build_lookup_tables.py <input_dir> <data_dir>
"""
import csv
import json
import os
import re
import sys


def read_tables(path):
    """마크다운 파일의 <table> 블록들을 (시작 줄, [행(셀 리스트)]) 로 반환."""
    lines = open(path, encoding="utf-8").read().splitlines()
    out, i = [], 0
    while i < len(lines):
        if lines[i].startswith("<table>"):
            start, rows = i + 1, []
            i += 1
            while i < len(lines) and not lines[i].startswith("</table>"):
                cells = [c.strip().replace("**", "") for c in lines[i].strip().strip("|").split("|")]
                rows.append(cells)
                i += 1
            out.append((start, rows))
        i += 1
    return out


def unit(id_, title, src, data, note=None):
    u = {"id": id_, "kind": "table", "source": src, "text": {"summary": title},
         "mech": {"schema": "lookup_table", "confidence": "auto", "coverage": "full", "data": data}}
    if note:
        u["text"]["note"] = note
    return u


def damage_chart(input_dir):
    path = os.path.join(input_dir, "ch07-combat.md")
    for start, rows in read_tables(path):
        if rows and rows[0][0].startswith("굴림(Rolled) 데미지"):
            chart = {}
            for r in rows[2:]:
                # | 1 | 1d6+1 | 15 | 4d10+20 | 1 | 2 / 5 / 7 | 15 | 24 / 45 / 60 |
                for db, dice in ((r[0], r[1]), (r[2], r[3])):
                    chart.setdefault(int(db), {})["dice"] = dice
                for db, setv in ((r[4], r[5]), (r[6], r[7])):
                    lo, mid, hi = [int(x) for x in re.findall(r"\d+", setv)]
                    chart.setdefault(int(db), {})["set"] = {"low": lo, "mid": mid, "high": hi}
            return unit("combat/damage-chart", "데미지 표: 기본 데미지 -> 실제 데미지(굴림/지정)",
                        {"chapter": "ch07-combat", "line": start}, {"by_damage_base": {str(k): v for k, v in sorted(chart.items())}})
    raise SystemExit("damage chart not found")


def stage_table(input_dir):
    path = os.path.join(input_dir, "ch07-combat.md")
    for start, rows in read_tables(path):
        if rows and rows[0][:2] == ["전투단계", "승수"]:
            data = {r[0]: float(r[1].replace("x", "").strip()) for r in rows[1:]}
            return unit("combat/combat-stage-multipliers", "전투단계 승수 표", {"chapter": "ch07-combat", "line": start}, {"multiplier_by_stage": data})
    raise SystemExit("stage table not found")


def skill_rank_table(input_dir):
    path = os.path.join(input_dir, "ch03-skills-edges-feats.md")
    for start, rows in read_tables(path):
        if rows and rows[0][0].startswith("랭크 #"):
            data = {}
            for r in rows[1:]:
                name = re.sub(r"\(.*?\)", "", r[1]).strip()
                data[name] = {"rank": int(r[0]), "dice": r[2], "eng": re.search(r"\((.*?)\)", r[1]).group(1)}
            return unit("gameplay/skill-rank-dice", "스킬 랭크 -> 주사위 수", {"chapter": "ch03-skills-edges-feats", "line": start}, {"by_rank_name": data})
    raise SystemExit("skill rank table not found")


def type_chart(input_dir):
    rows = list(csv.reader(open(os.path.join(input_dir, "db", "nature-type.csv"), encoding="utf-8", newline="")))
    hdr = next(i for i, r in enumerate(rows) if r and r[0].startswith("방어v"))
    names, matrix = [], []
    for r in rows[hdr + 1:]:
        if not r or not r[0].strip() or not r[1].strip():
            break
        names.append(r[0].strip())
        matrix.append([float(x) for x in r[1:1 + 19]])
    # 행 = 방어 타입, 열 = 공격 타입 (열 순서는 행 순서와 같다: 시트 헤더가 일부만 채워져 있어 행 순서로 보정)
    # 마지막 행 'None'(무타입 방어)은 열에는 없다.
    atts = names[:len(matrix[0])]
    chart = {att: {dfn: matrix[j][i] for j, dfn in enumerate(names)} for i, att in enumerate(atts)}
    return unit("combat/type-chart", "타입 상성표 (공격 타입 -> 방어 타입 -> 배수)",
                {"sheet": "데이터베이스 버전.9세대 / 성격/타입 정보", "row": hdr + 1},
                {"attack_vs_defense": chart, "types": names},
                note="룰북 본문(ch07 '타입 상성')의 표는 이미지([img])라 텍스트 추출 불가. 시트에서 가져옴. 열 라벨이 일부 비어 있어 행 순서로 복원.")


def nature_table(input_dir):
    rows = list(csv.reader(open(os.path.join(input_dir, "db", "nature-type.csv"), encoding="utf-8", newline="")))
    data = {}
    for r in rows[1:]:
        if not r or not r[0].strip() or r[0].startswith("방어v"):
            if r and r[0].startswith("방어v"):
                break
            continue
        data[r[0].strip()] = {"up": r[1].strip(), "down": r[2].strip(), "likes": r[3].strip(), "dislikes": r[4].strip(), "eng": r[12].strip() if len(r) > 12 else None}
    return unit("pokemon/natures", "성격표: 상승/하강 스탯과 맛 선호", {"sheet": "데이터베이스 버전.9세대 / 성격/타입 정보"}, {"by_name": data})


def weight_class_table(input_dir):
    """Preserve the reference rows, including shared endpoints and class7 condition."""
    path = os.path.join(input_dir, "ch10-index-reference.md")
    for start, rows in read_tables(path):
        if rows and rows[0][0] == "무게 등급 1":
            if len(rows) != 7:
                raise ValueError("weight class reference requires all seven source rows")
            by_class = {}
            for number, row in enumerate(rows, 1):
                if len(row) != 2 or row[0] != f"무게 등급 {number}" or not row[1]:
                    raise ValueError("ordered weight class label and source description required")
                by_class[str(number)] = {"label": row[0], "description": row[1]}
            return unit("pokemon/weight-classes", "무게 등급표: 원문 범위와 조건",
                        {"chapter": "ch10-index-reference", "line": start},
                        {"by_weight_class": by_class},
                        note="원문 경계와 단위·헤비메탈 조건을 보존한다. 이 조회 표는 질량에서 등급을 자동 추정하지 않는다.")
    raise ValueError("weight class reference table not found")


def main(input_dir, data_dir):
    os.makedirs(data_dir, exist_ok=True)
    units = [damage_chart(input_dir), stage_table(input_dir), skill_rank_table(input_dir), type_chart(input_dir), nature_table(input_dir), weight_class_table(input_dir)]
    json.dump(units, open(os.path.join(data_dir, "lookup-tables.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    for u in units:
        d = u["mech"]["data"]
        print(u["id"], "->", {k: (len(v) if isinstance(v, (dict, list)) else v) for k, v in d.items()})


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
