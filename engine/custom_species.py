"""
커스텀 포켓몬(종) 적재 방법론 — 파일 하나로 종·학습·특성·기술까지 들여온다.
파일 꼴 (data/custom/species/<이름>.json):
{
  "name": "실험체", "eng": "Specimen", "dex": "C001", "types": ["전기", "고스트"],
  "base_stats": {"hp": 6, "atk": 5, "def": 5, "spa": 9, "spd": 6, "spe": 8},
  "movement": {"land": 5, "sky": 0, "swim": 2, "levitate": 4, "burrow": 0, "high_jump": 1, "long_jump": 1, "power": 1},
  "capabilities": ["빛내기", "텔레파시"], "size": "소형", "weight_class": 1, "egg_groups": ["무정형"], "naturewalk": "도시",
  "evolution": ["1 - 실험체", "2 - 실험체Ω 30이상"],
  "abilities": {"기본 특성": ["부유", "정전기"], "숨겨진 특성": ["트레이스"], "대단한 특성": ["클리어바디"]},
  "learnset": {"level_up": [{"level": 1, "move": "전기쇼크"}, {"level": 7, "move": "섀도볼"}, {"level": 12, "move": "오버로드"}], "tm": ["10만볼트"], "egg": [], "tutor": []},
  "skills": {"곡예": 2, "육상": 2, "전투": 2, "명령": 1, "직감": 3, "집중": 3, "은신": 4},
  "custom_abilities": { "정전기Ω": {"frequency": "항상", "effect": "…", "mech": [{"type": "trigger", "text": "근접 공격을 당했을 경우"}, {"type": "apply_status", "status": "마비", "target": "target"}]} },
  "custom_moves": [ {"name": "오버로드", "type": "전기", "class": "특수", "damage_base": 9, "ac": 3, "frequency": "장면 x2", "range": "6, 대상 1", "effect": "…",
                     "mech": [{"type": "apply_status", "status": "마비", "target": "target", "on_natural_roll_min": 17}]} ],
  "source": "custom", "author": "…", "notes": "…"
}
검증(validate): 타입 이름, 기본 스탯 6개(1 이상, 합계가 DB 분포의 [min, max] 안이면 통과·밖이면 경고), 이동 키, 크기/체급, 학습 기술이 DB 또는 custom_moves 에 있는지(이름 별칭 적용),
특성이 DB 또는 custom_abilities 에 있는지, custom_moves 의 mech effect 가 어휘에 있는 유형인지. 오류는 예외, 경고는 목록으로 돌려준다.
적재(load_and_validate): Rules.species / learnsets / learnset_links / species_skills 에 합치고, custom_moves 는 Rules.moves + moves_mech(헤더) + moves_reviewed(effects, confidence 'custom'),
custom_abilities 는 Rules.ability_effects / ability_freq 에 넣는다. 종·기술·특성 모두 출처 'custom' 표식이 붙어 룰셋 필터(출처 그룹 custom)로 끄고 켤 수 있다.
"""
import json
import os
import re

TYPES = ["노말", "격투", "비행", "독", "땅", "바위", "벌레", "고스트", "강철", "불꽃", "물", "풀", "전기", "에스퍼", "얼음", "드래곤", "악", "페어리"]
STATS = ["hp", "atk", "def", "spa", "spd", "spe"]
MOVE_KEYS = ["land", "sky", "swim", "levitate", "burrow", "high_jump", "long_jump", "power"]
SIZES = ["소형", "중형", "대형", "거대", "초거대"]


def slug(s):
    return re.sub(r"[^0-9A-Za-z가-힣]+", "-", re.sub(r"\[.*?\]|\(.*?\)", "", s)).strip("-").lower()


def norm(n):
    return re.sub(r"\s+|\*|§|\[.*?\]|\(.*?\)", "", n)


def parse_range(raw):
    out = {"raw": raw, "parsed": False}
    m = re.match(r"^(근접|자신|전체|\d+)\s*(?:,\s*대상\s*(\d+))?", raw)
    if m:
        out["origin"] = "melee" if m.group(1) == "근접" else "self" if m.group(1) == "자신" else "field" if m.group(1) == "전체" else int(m.group(1))
        if m.group(2):
            out["targets"] = int(m.group(2))
    m = re.search(r"(파열|원뿔|직선|인접 폭발|원거리 폭발)\s*(\d+)", raw)
    if m:
        out["shape"] = {"파열": "burst", "원뿔": "cone", "직선": "line", "인접 폭발": "close_blast", "원거리 폭발": "blast"}[m.group(1)]
        out["size"] = int(m.group(2))
    out["parsed"] = "origin" in out or "shape" in out
    return out


def parse_frequency(raw):
    raw = str(raw or "임의")
    if raw.startswith("임의") or raw.startswith("자유"):
        return {"kind": "at_will"}
    if raw.startswith("턴1회") or "턴 1회" in raw:
        return {"kind": "every_other_turn"}
    m = re.match(r"(장면|하루|일일)\s*x?\s*(\d+)?", raw)
    if m:
        return {"kind": "scene" if m.group(1) == "장면" else "daily", "uses": int(m.group(2) or 1)}
    return {"kind": "unknown", "raw": raw}


def validate(rules, data):
    """(오류 목록, 경고 목록). 오류가 있으면 적재하지 않는다."""
    errors, warns = [], []
    name = data.get("name")
    if not name or not isinstance(name, str):
        errors.append("name 없음")
    types = data.get("types") or []
    if not (1 <= len(types) <= 2) or any(t not in TYPES for t in types):
        errors.append(f"types 는 1~2개의 타입 이름이어야 함: {types}")
    bs = data.get("base_stats") or {}
    if set(bs) != set(STATS) or any(not isinstance(bs[s], int) or bs[s] < 1 for s in STATS if s in bs):
        errors.append(f"base_stats 는 {STATS} 각각 1 이상의 정수: {bs}")
    else:
        bst = sum(bs.values())
        sums = [sum(sp["base_stats"].values()) for sp in rules.species.values() if sp.get("source", "db") != "custom" and sp.get("base_stats")]
        if sums:
            lo, hi = min(sums), max(sums)
            if not (lo <= bst <= hi):
                warns.append(f"기본 스탯 합 {bst} 이 DB 범위 [{lo}, {hi}] 밖 (의도한 것이면 무시)")
            # 같은 진화 단계 기준 분포: 상위 5% 밖이면 경고
            if bst > sorted(sums)[int(len(sums) * 0.95)]:
                warns.append(f"기본 스탯 합 {bst} 은 DB 상위 5% (전설급)")
    mv = data.get("movement") or {}
    bad = [k for k in mv if k not in MOVE_KEYS]
    if bad:
        errors.append(f"movement 키 이상: {bad} (허용 {MOVE_KEYS})")
    if "land" not in mv and "levitate" not in mv and "sky" not in mv and "swim" not in mv:
        warns.append("이동 재능이 하나도 없음 → land 4 로 간주")
    if data.get("size") and data["size"] not in SIZES:
        errors.append(f"size 는 {SIZES} 중 하나: {data.get('size')}")
    wc = data.get("weight_class", 1)
    if not isinstance(wc, int) or not (1 <= wc <= 7):
        errors.append(f"weight_class 는 1~7: {wc}")
    custom_moves = {m["name"]: m for m in data.get("custom_moves", []) if isinstance(m, dict) and m.get("name")}
    for cm in custom_moves.values():
        if cm.get("type") not in TYPES:
            errors.append(f"custom_move {cm['name']}: type 이상 {cm.get('type')}")
        if cm.get("class") not in ("물리", "특수", "변화"):
            errors.append(f"custom_move {cm['name']}: class 는 물리/특수/변화")
        if cm.get("class") in ("물리", "특수") and not isinstance(cm.get("damage_base"), int):
            errors.append(f"custom_move {cm['name']}: 공격기는 damage_base 정수 필요")
        if cm.get("damage_base") is not None and not (1 <= int(cm.get("damage_base") or 1) <= 28):
            errors.append(f"custom_move {cm['name']}: damage_base 는 1~28")
        try:
            import effects_ext  # noqa
            from effects import SUPPORTED
            for e in cm.get("mech") or []:
                if not isinstance(e, dict) or e.get("type") not in SUPPORTED:
                    warns.append(f"custom_move {cm['name']}: effect 유형 '{(e or {}).get('type') if isinstance(e, dict) else e}' 은 엔진 어휘에 없음 → GM 프롬프트로 소비")
        except Exception:
            pass
    move_names = {norm(m["name"]): m["id"] for m in rules.moves.values() if m.get("id") != "struggle"}
    ls = data.get("learnset") or {}
    for entry in ls.get("level_up", []):
        n = norm(str(entry.get("move", "")))
        if n not in move_names and entry.get("move") not in custom_moves:
            errors.append(f"학습 기술 '{entry.get('move')}' 이 DB 와 custom_moves 어디에도 없음")
        if not isinstance(entry.get("level"), int):
            errors.append(f"학습 기술 '{entry.get('move')}' 의 level 이 정수가 아님")
    custom_abilities = data.get("custom_abilities") or {}
    for group, names in (data.get("abilities") or {}).items():
        for a in names or []:
            if a not in rules.ability_effects and a not in custom_abilities and a not in rules.ability_freq:
                errors.append(f"특성 '{a}' 이 DB 와 custom_abilities 어디에도 없음")
    return errors, warns


def load_and_validate(rules, path):
    data = json.load(open(path, encoding="utf-8"))
    errors, warns = validate(rules, data)
    if errors:
        raise ValueError(f"커스텀 종 '{data.get('name')}' 검증 실패: " + "; ".join(errors))
    name = data["name"]
    sid = "pokemon/" + slug(name)
    sp = {"id": sid, "name": name, "eng": data.get("eng"), "dex": data.get("dex", "C???"), "base_stats": dict(data["base_stats"]), "types": list(data["types"]),
          "movement": {k: data.get("movement", {}).get(k, 0) for k in MOVE_KEYS}, "naturewalk": data.get("naturewalk"), "capabilities": list(data.get("capabilities") or []),
          "size": data.get("size", "중형"), "weight_class": data.get("weight_class", 1), "egg_groups": list(data.get("egg_groups") or []), "group": None,
          "source": "custom", "custom_file": os.path.basename(path), "author": data.get("author"), "notes": data.get("notes"), "warnings": warns}
    if not any(sp["movement"].values()):
        sp["movement"]["land"] = 4
    # 커스텀 기술 → Rules.moves / moves_mech(헤더) / moves_reviewed(effects)
    for cm in data.get("custom_moves", []):
        mid = "move/" + slug(cm["name"])
        rec = {"id": mid, "name": cm["name"], "eng": cm.get("eng"), "type": cm["type"], "class": cm["class"], "damage_base": cm.get("damage_base"), "ac": cm.get("ac"),
               "frequency": cm.get("frequency", "임의"), "range": cm.get("range", "근접, 대상 1"), "effect": cm.get("effect", ""), "contest": cm.get("contest"), "homebrew": False,
               "keywords": [k for k in ("우선", "방해", "반응", "강타", "이단타격", "오단타격", "소리", "가루", "치유", "밀기") if k in str(cm.get("range", ""))], "source": "custom", "mech_auto": {}}
        rules.moves[mid] = rec
        rules.moves_mech[mid] = {"name": cm["name"], "eng": cm.get("eng"), "confidence": "custom", "coverage": "full",
                                 "header": {"type": cm["type"], "class": cm["class"], "damage_base": cm.get("damage_base"), "ac": cm.get("ac"), "frequency": parse_frequency(cm.get("frequency")),
                                            "range": parse_range(cm.get("range", "근접, 대상 1")), "contest": cm.get("contest"), "keywords": rec["keywords"]},
                                 "effects": [], "narrative": [cm.get("effect", "")]}
        rules.moves_reviewed[mid] = {"effects": list(cm.get("mech") or []), "note": "custom move", "reviewer": data.get("author") or "custom"}
    # 커스텀 특성 → ability_effects / ability_freq
    for an, ad in (data.get("custom_abilities") or {}).items():
        rules.ability_effects[an] = list(ad.get("mech") or [])
        rules.ability_freq[an] = ad.get("frequency", "항상")
    rules.touch("moves", "moves_mech", "moves_reviewed", "ability_effects", "ability_freq")
    # 학습 데이터 (엔티티 꼴 + 링크 꼴)
    ls_raw = data.get("learnset") or {}
    move_names = {norm(m["name"]): m["id"] for m in rules.moves.values() if m.get("id") != "struggle"}
    level_up = [{"level": int(e["level"]), "move": e["move"], "type": rules.moves.get(move_names.get(norm(e["move"]), ""), {}).get("type")} for e in ls_raw.get("level_up", [])]
    ls = {"id": f"learnset/{slug(name)}", "species": name, "confidence": "custom", "level_up": level_up, "tm": list(ls_raw.get("tm") or []), "egg": list(ls_raw.get("egg") or []),
          "tutor": list(ls_raw.get("tutor") or []), "evolution": list(data.get("evolution") or [f"1 - {name}"]), "abilities": data.get("abilities") or {},
          "height_m": data.get("height_m"), "size": sp["size"], "weight_kg": data.get("weight_kg"), "weight_class": sp["weight_class"], "diet": data.get("diet"), "habitat": data.get("habitat"), "hatch": data.get("hatch"), "note": data.get("notes", "")}
    links = {"species": name, "moves": [{"to": move_names[norm(e["move"])], "source": "level_up", "level": e["level"]} for e in level_up if norm(e["move"]) in move_names]
             + [{"to": move_names[norm(re.sub(r"^(A?\d+)\s+", "", n))], "source": "tm"} for n in ls["tm"] if norm(re.sub(r"^(A?\d+)\s+", "", n)) in move_names],
             "abilities": [{"to": f"ability/{slug(a)}", "slot": g} for g, names in ls["abilities"].items() for a in names or []], "unresolved": []}
    skills = {k: {"rank": int(v), "mod": "+0"} for k, v in (data.get("skills") or {}).items()} or None
    return sp, ls, links, skills


def template_from(rules, species_name, new_name, author=None):
    """기존 종을 본으로 커스텀 종 파일 초안을 만든다 (tools/new_species.py)."""
    from builder import species_lookup
    sp = species_lookup(rules, species_name)
    ls = rules.learnsets.get(sp["name"], {})
    return {"name": new_name, "eng": None, "dex": "C???", "types": list(sp["types"]), "base_stats": dict(sp["base_stats"]), "movement": dict(sp.get("movement") or {}),
            "capabilities": list(sp.get("capabilities") or []), "size": sp.get("size", "중형"), "weight_class": sp.get("weight_class", 1), "egg_groups": list(sp.get("egg_groups") or []),
            "naturewalk": sp.get("naturewalk"), "evolution": [f"1 - {new_name}"], "abilities": ls.get("abilities") or {},
            "learnset": {"level_up": [{"level": e["level"], "move": e["move"]} for e in ls.get("level_up", [])], "tm": list(ls.get("tm") or []), "egg": list(ls.get("egg") or []), "tutor": list(ls.get("tutor") or [])},
            "skills": {k: v.get("rank", 1) for k, v in (rules.species_skills.get(sp["name"]) or {}).items()},
            "custom_abilities": {}, "custom_moves": [], "source": "custom", "author": author, "notes": f"{sp['name']} 을(를) 본으로 만든 초안 — 스탯·타입·학습을 고쳐 쓰세요."}
