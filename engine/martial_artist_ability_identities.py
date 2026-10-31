"""Stable Martial Artist Ability identities with separately sourced core bodies.

The existing class acquisition provenance remains unchanged. The selected core
bodies come from abilities-core.json and the registered English source; the
separately selectable Playtest declarations remain independent.
"""
from copy import deepcopy
from hashlib import sha256
from pathlib import Path


SOURCE_FILE = "input/ch04-trainer-classes.md"
SOURCE_SHA256 = "a1a4a213074bc6166507db3e0d4c04ded02c04168c4798c636a4d53911494ac4"
SOURCE_LINES = [2394, 2402]
EXCERPT_SHA256 = "2f481f1d92929baab079707d33c55a06ad4240882f722574fb197aaeaa39bf00"
PARENT = "class/무술가"
DERIVED = {
    "ability/정신력": {"title": "정신력", "eng": "Inner Focus"},
    "ability/이판사판": {"title": "이판사판", "eng": "Reckless"},
}


def install(rules):
    path = Path(rules.root) / SOURCE_FILE
    if sha256(path.read_bytes()).hexdigest() != SOURCE_SHA256:
        raise ValueError("Martial Artist source changed; derived Ability identities require review")
    lines = path.read_text(encoding="utf-8").splitlines()
    excerpt = "\n".join(lines[SOURCE_LINES[0] - 1:SOURCE_LINES[1]])
    if sha256(excerpt.encode("utf-8")).hexdigest() != EXCERPT_SHA256:
        raise ValueError("Martial Artist Ability-choice text changed; review required")
    for uid, row in DERIVED.items():
        if uid not in rules.selection.units:
            rules.selection.register_derived({
                "id": uid,
                "title": row["title"],
                "eng": row["eng"],
                "kind": "entity:ability",
                "source": {
                    "file": SOURCE_FILE.removeprefix("input/"),
                    "lines": list(SOURCE_LINES),
                    "sha256": SOURCE_SHA256,
                    "path": ["Chapter 4 : 트레이너 클래스", "파이터 클래스(Fighter Classes)", "무술가"],
                },
                "tags": ["source-scoped", "identity-only"],
                "keyword": None,
                "source_group": None,
            }, (PARENT,))
        unit = rules.selection.units[uid]
        if (unit.get("title") != row["title"] or unit.get("eng") != row["eng"] or
                unit.get("source", {}).get("file") != SOURCE_FILE.removeprefix("input/") or
                unit.get("source", {}).get("lines") != SOURCE_LINES or
                unit.get("source", {}).get("sha256") != SOURCE_SHA256):
            raise ValueError("Martial Artist derived Ability identity changed: " + uid)
        # Identity and ownership are executable. The class source does not print
        # the separately versioned Ability body, so no passive effect is inferred.
        validate_core_definition(rules,rules.core_abilities[uid])
        rules.ability_effects[row['title']]=deepcopy(rules.core_abilities[uid]['effects'])
        rules.ability_freq.setdefault(row["title"], "항상")
        rules.touch("ability_effects", "ability_freq")
    return tuple(DERIVED)


def validate_core_definition(rules,row):
    expected={
      'ability/정신력':{'type':'martial_core','flinch_immunity':True,'initiative_zero_immunity':True},
      'ability/이판사판':{'type':'martial_core','damage_base':2,'moves':['move/점프킥','move/무릎차기'],'keyword':'반동'}}
    uid=row.get('id');definition=DERIVED.get(uid)
    if definition is None or row.get('native_contract')!=expected[uid] or row.get('name')!=definition['title'] or row.get('eng')!=definition['eng']:raise ValueError('reviewed core Martial Ability contract required')
    if row.get('keyword')!=('방어적' if uid=='ability/정신력' else None):raise ValueError('core Martial Ability keyword changed')
    expected_effects=[{'type':'immunity','status':'풀죽음'}] if uid=='ability/정신력' else []
    if row.get('effects')!=expected_effects:raise ValueError('core Martial Ability effect projection changed')
    authority=row['official_source'];path=Path(rules.root)/authority['file']
    if sha256(path.read_bytes()).hexdigest()!=authority['sha256']:raise ValueError('core Martial Ability English source changed')
    text=path.read_text(encoding='utf8').splitlines();start,end=authority['lines']
    if text[start-1]!='Ability: '+definition['eng'] or text[end-1]!=row['effect']:raise ValueError('core Martial Ability body/source mismatch')
    return row


def blocks_zero(actor,operation):
    import ability_transitions as A
    return operation.get('operation')=='replace' and operation.get('value')==0 and A.active(actor,'ability/정신력')


def damage_base_bonus(engine,actor,move):
    import ability_transitions as A
    if not A.active(actor,'ability/이판사판'):return 0
    row=validate_core_definition(engine.r,engine.r.core_abilities['ability/이판사판']);contract=row['native_contract']
    return contract['damage_base'] if move['id'] in contract['moves'] or contract['keyword'] in str(move.get('range','')) or 'Recoil' in str(move.get('keywords',[])) else 0
