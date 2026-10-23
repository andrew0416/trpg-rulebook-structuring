"""Selected core class moves, preserving each acquired rank and source owner.

This projects already-acquired features; it does not award acquisition stats or
approve a new class. Printed move-selection restrictions are validated before
any list or source mutation. CSV variants are deliberately not aliases.
"""
import hashlib
import json
from pathlib import Path

import acquired_features as ACQUIRED
import skill_modifiers as SKILLS
import state_grants as GRANTS

CORE_FIXED = {
    "class/선동가": ("천사의키스", "도발"),
    "class/로그": ("속여때리기", "도둑질"),
    "feat/금술": ("대타출동", "맹독"),
    "feat/pk-알파": ("숟가락휘기", "배리어"),
    "feat/정신공격": ("신통력", "사이코쇼크"),
    "feat/바위-파편": ("스톤샤워", "스텔스록"),
}

# Pure fixed move-pair receipts. Their CSV clauses contain no activation,
# alternate choice, weapon permission, or other executable obligation.
FIXED_CSV_PAIRS = {
    "feat/달맞이산-블루스": ("노래하기", "초음파"),
    "feat/불협화음": ("싫은소리", "금속음"),
    "feat/소음-신고": ("소란피기", "하이퍼보이스"),
    "feat/엇갈린-메시지": ("악마의키스", "트집"),
    "feat/불시의-공격": ("따라가때리기", "기습"),
    "feat/거리의-싸움꾼": ("승부굳히기", "보복"),
    "feat/악감정": ("검은눈빛", "야금야금"),
    "feat/잔혹한-응시": ("뱀눈초리", "박치기"),
    "feat/굳건함": ("버티기", "게으름피우기"),
    "feat/위에서-내려온-죽음": ("애크러뱃", "뛰어오르기"),
    "feat/신성-방패": ("리플렉터", "주술"),
    "feat/신비의-방어": ("빛의장막", "신비의부적"),
    "feat/pk-오메가": ("텔레키네시스", "사이코키네시스"),
    "feat/연마된-정신": ("마음의눈", "명상"),
    "feat/공간-왜곡": ("순간이동", "사이드체인지"),
    "feat/지면-뒤틀기": ("중력", "트릭"),
    "feat/이상한-힘": ("회복봉인", "매직코트"),
    "feat/철벽": ("철벽", "방어"),
    "feat/선명한-그림자": ("악의파동", "깜짝베기"),
    "feat/심연의-심장": ("나이트버스트", "혼내기"),
    "feat/정열적인-하모니": ("매지컬샤인", "드레인키스"),
    "feat/럭키-클로버-그랜드-피날레": ("문포스", "아로마미스트"),
    "feat/불쾌함의-부름": ("녹기", "오물폭탄"),
    "feat/불쾌함-촉발": ("오물웨이브", "맹독"),
}
FIXED = {**CORE_FIXED, **FIXED_CSV_PAIRS}
AURA = "class/파동술사"
RANKED = {
    "feat/겨울의-예고": {1: ("프리즈드라이", "냉동펀치", "냉동빔", "고드름떨구기"),
                       2: ("눈사태", "눈보라", "얼음숨결", "고드름침")},
    "feat/육상-기술": {1: ("조이기", "블록", "힘껏치기", "괴력"),
                    2: ("누르기", "돌진", "신속"), 3: ("메가톤킥", "객기", "원수갚기")},
    "feat/무술-훈련": {1: ("경혈찌르기", "손바닥치기", "두번차기", "기충전", "태권당수", "로킥", "마하펀치", "돌려차기", "받아던지기"),
                    2: ("깨트리기", "배대뒤치기", "연속펀치", "카운터", "안다리걸기", "점프킥", "파워트릭", "패스트가드"),
                    3: ("크로스촙", "인파이트", "트리플킥", "무릎차기", "스카이어퍼", "업어후리기")},
    "feat/오컬트-마니아-연구": {1: ("이상한빛", "저주", "최면술", "원한", "도깨비불"), 2: (), 3: ("병상첨병",)},
}
MARTIAL_ABILITIES = {
    "경혈찌르기": "ability/유연", "손바닥치기": "ability/테크니션", "태권당수": "ability/정신력", "마하펀치": "ability/철주먹", "돌려차기": "ability/이판사판", "받아던지기": "ability/근성",
    "배대뒤치기": "ability/근성", "연속펀치": "ability/철주먹", "카운터": "ability/유연", "안다리걸기": "ability/정신력", "점프킥": "ability/이판사판", "파워트릭": "ability/유연", "패스트가드": "ability/테크니션",
    "크로스촙": "ability/정신력", "트리플킥": "ability/테크니션", "무릎차기": "ability/이판사판", "스카이어퍼": "ability/철주먹", "업어후리기": "ability/근성",
}
TABLED_RANKED = ("feat/스톰-위자드", "feat/휘몰아치는-바람", "feat/자연의-포용", "feat/해류의-부름")
RANKED_POLICY = "data/class-ranked-move-tables.json"
SOURCES = (*FIXED, AURA, *RANKED, *TABLED_RANKED)
SKILL_DOMAINS = {"class/선동가": ("매력", "교활", "협박"), "class/로그": ("곡예", "육상", "은신")}


def _ranked_tables(rules):
    cached = getattr(rules, "_ranked_class_move_tables", None)
    if cached is not None:
        return cached
    path = Path(rules.root) / RANKED_POLICY
    if not path.is_file():
        path = Path(__file__).resolve().parent.parent / RANKED_POLICY
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("schema_version") != 1 or set(data.get("rules", {})) != set(TABLED_RANKED):
        raise ValueError("unsupported ranked class move table policy")
    source = Path(rules.root) / data["source_file"]
    if hashlib.sha256(source.read_bytes()).hexdigest() != data["source_sha256"]:
        raise ValueError("ranked class move source changed")
    lines = source.read_text(encoding="utf-8").splitlines()
    for uid, row in data["rules"].items():
        binding = rules.selection.units.get(uid, {}).get("source", {})
        bounds = row["lines"]
        excerpt = "\n".join(lines[bounds[0]-1:bounds[1]])
        if ("input/" + str(binding.get("file", "")) != data["source_file"]
                or binding.get("sha256") != data["source_sha256"]
                or binding.get("lines") != bounds
                or hashlib.sha256(excerpt.encode()).hexdigest() != row["excerpt_sha256"]):
            raise ValueError("ranked class move source binding changed: " + uid)
        moves = [mid for group in row["moves_by_rank"].values() for mid in group]
        if (set(row["moves_by_rank"]) != {"1", "2", "3"}
                or len(set(moves)) != len(moves)
                or any(not mid.startswith("move/") or mid not in rules.selection.units for mid in moves)
                or not set(row.get("branch_for_move", {})).issubset(moves)
                or row["parent"] not in rules.selection.units):
            raise ValueError("ranked class move table binding changed: " + uid)
    rules._ranked_class_move_tables = data["rules"]
    return data["rules"]


def _ranked_context(actor, uid, rank):
    row = _ranked_tables(actor.r)[uid]
    effects, header = actor.r.feat_effects(uid)
    frequency = header.get("frequency", {})
    if effects != row["effects"] or frequency.get("kind") != "static" or frequency.get("action") != "static":
        raise ValueError("ranked class move declaration changed: " + uid)
    parent = row["parent"]
    branch = None
    if row.get("branch_for_move"):
        import static_feature_state_grants as STATIC
        branch = STATIC.class_branch(actor, parent)
        owns_parent = branch is not None
    else:
        owns_parent = _owned(actor, parent) and actor.r._selected_rule(parent) == parent
    minimum = row["minimum_skill_rank"][rank-1]
    if not owns_parent or (minimum and not any(_skill(actor, skill) >= minimum for skill in row["skills"])):
        raise ValueError("ranked class move prerequisite is not established: " + uid)
    return row, branch


def identity(rules, name):
    if not isinstance(name, str):
        raise ValueError("class move source must be a text identity")
    found = [uid for uid in SOURCES if name in (uid, rules.selection.units[uid]["title"], rules.selection.units[uid].get("eng"))]
    if len(found) > 1:
        raise ValueError("ambiguous class move source")
    return found[0] if found else None


def _owned(actor, uid):
    unit = actor.r.selection.units[uid]
    aliases = {uid, unit["title"], unit.get("eng")}
    count = 0
    for field in ("classes", "feats", "edges"):
        values = actor.spec.get(field, [])
        if not isinstance(values, (list, tuple)):
            raise ValueError("acquired class/feature list required")
        local = sum(value in aliases for value in values)
        if local > 1:
            raise ValueError("duplicate acquired class move source")
        # The conventional class reference in feats and classes is one identity.
        count = max(count, local) if uid.startswith("class/") else count + local
    if count > 1:
        raise ValueError("duplicate acquired class move source")
    return bool(count)


def _skill(actor, skill):
    return SKILLS.rank(actor.r, actor, skill)[2]


def _prerequisites(engine, actor, uid, rank):
    supplemental = {
        "feat/겨울의-예고": (None, ("육상", "생존"), {1:5, 2:6}.get(rank,99)),
        "feat/바위-파편": (None, ("전투", "생존"), 5),
    }
    if uid in supplemental:
        parent, skills, minimum = supplemental[uid]
        if (parent is not None and not _owned(actor,parent)) or not any(_skill(actor,skill)>=minimum for skill in skills):
            raise ValueError("supplemental move prerequisite is not established: " + uid)
    if uid == "class/로그" and sum(_skill(actor, x) >= 3 for x in SKILL_DOMAINS[uid]) < 2:
        raise ValueError("Rogue requires two Novice Rogue Skills")
    if uid == "class/선동가" and not any(_owned(actor, x) for x in ("edge/신뢰있는-아티스트", "edge/협박하는-존재", "edge/호감인")):
        raise ValueError("Provocateur requires its acquired social edge")
    if uid == AURA:
        import elemental_connection as ELEMENTAL
        if "격투" not in ELEMENTAL.choices(engine, actor):
            raise ValueError("Aura Guardian requires Fighting Elemental Connection")
    conditions = {
        "feat/금술": ("feat/독극-무기", "은신", 6),
        "feat/pk-알파": ("class/염동력자", None, 0),
        "feat/육상-기술": ("class/운동선수", "육상", {1: 0, 2: 5, 3: 6}.get(rank, 99)),
        "feat/무술-훈련": ("class/무술가", "전투", {1: 0, 2: 5, 3: 6}.get(rank, 99)),
        "feat/오컬트-마니아-연구": ("class/오컬트마니아", "오컬트학", 5 if rank == 3 else 0),
    }
    if uid in conditions:
        source, skill, minimum = conditions[uid]
        if not _owned(actor, source) or (minimum and _skill(actor, skill) < minimum):
            raise ValueError("class move prerequisite is not established: " + uid)


def _choices(actor, uid):
    choices = actor.spec.get("feature_choices", {})
    if not isinstance(choices, dict):
        raise ValueError("feature choices must be a mapping")
    matches = [value for key, value in choices.items() if identity(actor.r, key) == uid]
    if len(matches) > 1:
        raise ValueError("duplicate aliases for class move choices")
    return matches[0] if matches else None


def _pair(rules, pair, allowed):
    if not isinstance(pair, (list, tuple)) or len(pair) != 2:
        raise ValueError("exactly two selected class moves required per acquisition")
    values = [rules.move_id(value) if isinstance(value, str) else None for value in pair]
    allowed = {rules.move_id(value) for value in allowed}
    if None in values or len(set(values)) != 2 or any(value not in allowed for value in values):
        raise ValueError("class move choice outside its printed rank/domain")
    return values


def plan(engine, actor, uid):
    if actor.kind != "trainer" or not _owned(actor, uid):
        raise ValueError("actual trainer acquisition required")
    if engine.r._selected_rule(uid) != uid:
        raise ValueError("selected class move variant requires its own policy")
    rank = ACQUIRED.feature_rank(actor, uid) if uid in RANKED or uid in TABLED_RANKED else 1
    table, branch = _ranked_context(actor, uid, rank) if uid in TABLED_RANKED else (None, None)
    _prerequisites(engine, actor, uid, rank)
    chosen = _choices(actor, uid)
    if uid in FIXED:
        if chosen is not None:
            raise ValueError("fixed class move source has no selectable moves")
        groups = [_pair(engine.r, FIXED[uid], FIXED[uid])]
    elif uid == AURA:
        groups = [_pair(engine.r, chosen, ("판별", "진공파", "발경"))]
    else:
        if not isinstance(chosen, (list, tuple)) or len(chosen) != rank:
            raise ValueError("one explicit two-move selection per acquired rank required")
        groups = []
        martial_ability = None
        if uid == "feat/무술-훈련":
            import trainer_feature_acquisition as ACQUISITION
            martial_ability = ACQUISITION.martial_ability(actor)
        for number, pair in enumerate(chosen, 1):
            if table is not None:
                allowed = [move for level, moves in table["moves_by_rank"].items() if int(level) <= number
                           for move in moves if table.get("branch_for_move", {}).get(move, branch) == branch]
            else:
                allowed = [move for level, moves in RANKED[uid].items() if level <= number for move in moves]
            group = _pair(engine.r, pair, allowed)
            if uid == "feat/무술-훈련":
                for name, ability in MARTIAL_ABILITIES.items():
                    if engine.r.move_id(name) in group and ability != martial_ability:
                        raise ValueError("selected Martial Artist move requires exact acquired Ability receipt: " + ability)
            groups.append(group)
        if len({value for group in groups for value in group}) != rank * 2:
            raise ValueError("ranked selections must learn distinct moves")
    return {"rule_id": uid, "rank": rank, "selections": groups,
            "moves": [value for group in groups for value in group]}


def skill_domain(actor, source):
    uid = identity(actor.r, source)
    if uid not in SKILL_DOMAINS or not _owned(actor, uid):
        raise ValueError("actual acquired class skill domain required")
    return SKILL_DOMAINS[uid]


def register_all(engine, actor):
    if actor.kind != "trainer":
        return 0
    selected = [plan(engine, actor, uid) for uid in SOURCES if _owned(actor, uid)]
    existing = actor.spec.get(GRANTS.KEY, {}).get("sources", {})
    managed = {key: value for key, value in existing.items() if value.get("class_move_projection") == 1}
    desired = {"feature:" + actor.entity_id + ":" + value["rule_id"]: value for value in selected}
    for key, value in desired.items():
        previous = managed.get(key, {}).get("class_move_selection")
        if previous is not None:
            selections = value["selections"]
            common = min(len(previous), len(selections))
            if previous[:common] != selections[:common]:
                raise ValueError("acquired class move selections cannot be silently replaced")
    changed = set(managed) != set(desired) or any(managed.get(key, {}).get("class_move_selection") != value["selections"] for key, value in desired.items())
    if not changed:
        return 0
    def apply(e, c):
        for key in managed:
            if key not in desired or managed[key].get("class_move_selection") != desired[key]["selections"]:
                GRANTS.revoke(c, key, engine=e)
        for key, value in desired.items():
            uid = value["rule_id"]
            GRANTS.grant_moves(c, value["moves"], key, "feature", owner_id=c.entity_id,
                               lifetime="while_owned", rule_id=uid, tutor_points=0)
            row = GRANTS.state(c)["sources"][key]
            row.update(class_move_projection=1, class_move_selection=value["selections"])
        return len(desired)
    return GRANTS.transition(engine, actor, apply)


def uses_ghost_curse(actor, move):
    """ch04:2915 applies only to Curse still supplied by Hex Maniac Studies.

    This is a move-local branch, never a change to actor type, STAB, affinity or
    any other Ghost-only prerequisite. Removing that source removes the exception
    even when a permanent or independent Curse source remains.
    """
    uid = "feat/오컬트-마니아-연구"
    mid = move.get("id") if isinstance(move, dict) else move
    if mid != "move/저주" or actor.kind != "trainer" or not _owned(actor, uid):
        return False
    if actor.r._selected_rule(uid) != uid:
        raise ValueError("selected Hex Maniac Studies variant requires its own policy")
    row = actor.spec.get(GRANTS.KEY, {}).get("sources", {}).get("feature:" + actor.entity_id + ":" + uid, {})
    return row.get("class_move_projection") == 1 and mid in row.get("grants", {}).get("moves", [])


def prepare_curse(engine, actor, target, move, mechanics, *, allow_approach=False):
    """Promote the printed ghost-Curse 8m target to the native move geometry.

    The nested reviewed range must match the exact source shape before removal;
    its meaning is enforced at the move boundary, before frequency, HP or RNG.
    """
    import move_type_sync as MOVE_SYNC
    move, mechanics = MOVE_SYNC.prepare_mechanics(engine, actor, move, mechanics)
    if not uses_ghost_curse(actor, move):
        return move, mechanics
    from copy import deepcopy
    from grid import cheb
    if not allow_approach and cheb(actor.pos, target.pos) > 8:
        raise ValueError("Hex Maniac Curse target must be within eight metres")
    projected, result = dict(move, range="8, 대상 1", _class_move_range={"origin":8,"targets":1,"raw":"8, 대상 1","parsed":True}), deepcopy(mechanics)
    branches = [effect for effect in result.get("effects_exec", [])
                if effect.get("type") == "alternate_effect" and effect.get("if") == "user is 고스트"]
    if len(branches) != 1:
        raise ValueError("selected Curse ghost branch requires an explicit source adapter")
    statuses = [effect for effect in branches[0].get("then", []) if effect.get("type") == "apply_status"]
    if len(statuses) != 1 or statuses[0] != {"type": "apply_status", "status": "저주", "target": "target", "range": "8m"}:
        raise ValueError("selected Curse range/status shape disagrees with the reviewed source")
    statuses[0].pop("range")
    # Frequency is consumed by frequency.move_frequency, not a persistent actor
    # modifier. Keeping this row would register a new passive on every cast.
    result["effects_exec"] = [effect for effect in result["effects_exec"] if effect.get("type") != "frequency_rule"]
    return projected, result
