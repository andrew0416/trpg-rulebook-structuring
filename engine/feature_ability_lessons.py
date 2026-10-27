"""Permanent Pokemon Ability lessons compose the existing clock and payment."""
import hashlib
import json
import csv
import io
from pathlib import Path

import ability_transitions as ABILITIES
import activity_jobs as JOBS
import common_checks as CHECKS
import grant_payments as PAYMENTS
import pokemon_teaching as TEACHING
import state_grants as GRANTS
import turn as TURN
import world_entities as WORLD

SOURCES = ("feat/효과적인-방법", "feat/댄스-연습", "feat/집단-전술", "feat/요리-음미", "feat/래밍-스피드", "feat/생기활발")
VIM = 'feat/생기활발'
LEGACY_SOURCES = SOURCES[:-1]
POLICY = "data/feature-ability-lessons.json"


def _same(left, right):
    return json.dumps(left,sort_keys=True,ensure_ascii=False,allow_nan=False)==json.dumps(right,sort_keys=True,ensure_ascii=False,allow_nan=False)


def _vim_rules(rules, rows, source_files):
    """Accept the reviewed five/six-rule policy; derive only absent Vim.

    Existing rows are never rewritten. Authenticated originals bind the source
    body/metadata, not a new fixture. Selected native effects/action are checked
    only by actual Vim qualification, not while another lesson loads policy.
    """
    if (type(rows)is not dict or set(rows) not in (set(LEGACY_SOURCES),set(SOURCES))
            or any(type(row)is not dict for row in rows.values())
            or type(source_files)is not dict):
        raise ValueError('unsupported Ability lesson policy')
    from source_context import verified_source
    feature_file='input/ch04-trainer-classes.md';ability_file='input/db/abilities.csv'
    pins={feature_file:'a1a4a213074bc6166507db3e0d4c04ded02c04168c4798c636a4d53911494ac4',
          ability_file:'87efebd17b0a5fe09c9db060a16a8844cf41be53d65eb35716cf62f80a177fae'}
    if any(source_files.get(path)!=digest for path,digest in pins.items()):
        raise ValueError('Vim lesson original source binding changed')
    text=verified_source(rules,{'file':feature_file,'sha256':pins[feature_file]},label='Vim lesson').decode('utf8').splitlines()
    bounds=[824,828]
    excerpt='\n'.join(text[bounds[0]-1:bounds[1]])
    excerpt_id='77fe196cd24b2fa5c02238a6ccea0ac9df356ea91da2cf5603c98756fcda5446'
    source=rules.selection.units.get(VIM,{}).get('source',{})
    if (len(text)<bounds[1] or hashlib.sha256(excerpt.encode()).hexdigest()!=excerpt_id
            or source.get('file')!='ch04-trainer-classes.md' or source.get('lines')!=bounds
            or source.get('sha256')!=pins[feature_file] or 'feat/떨쳐버리기' not in rules.selection.units):
        raise ValueError('Vim lesson actual source locator changed')
    content=verified_source(rules,{'file':ability_file,'sha256':pins[ability_file]},label='Vim Vigor choices')
    records=list(csv.reader(io.StringIO(content.decode('utf-8-sig'),newline='')))
    choices=[]
    for uid,title,number in (('ability/생기','생기',229),('ability/생기-홈브류','생기[홈브류]',684)):
        unit=rules.selection.units.get(uid,{});origin=unit.get('source',{})
        if (len(records)<number or not records[number-1] or records[number-1][0].replace(' ','')!=title
                or unit.get('title')!=title or origin.get('file')!='db/abilities.csv'
                or origin.get('record_span')!=[number,number] or origin.get('sha256')!=pins[ability_file]):
            raise ValueError('Vim lesson actual Vigor choice binding changed')
        choices.append({'id':uid,'title':unit['title'],'source_file':ability_file})
    expected={'clause_id':feature_file+':824-828','source_file':feature_file,'lines':bounds,
        'excerpt_sha256':excerpt_id,'parent':'feat/떨쳐버리기','own_pokemon':True,
        'once_per_pokemon':False,'point_cost':2,'abilities':choices,
        'effects':[{'type':'counter','name':'tutor_points','delta':-2,'target':'target'},
                   {'type':'grant_ability','grant_ability':choices[0]['title'],'on':'target'}]}
    if VIM in rows:
        declared=rows[VIM]
        if (type(declared)is not dict or set(declared)-set(expected)-{'source_note'}
                or any(key not in declared or not _same(declared[key],value) for key,value in expected.items())
                or ('source_note' in declared and not isinstance(declared['source_note'],str))):
            raise ValueError('Vim lesson reviewed declaration changed')
        return rows
    return {**rows,VIM:expected}


def identity(rules, value):
    if not isinstance(value, str):
        return None
    found = [uid for uid in SOURCES
             if value in (uid, rules.selection.units[uid]["title"], rules.selection.units[uid].get("eng"))]
    if len(found) > 1:
        raise ValueError("ambiguous Ability teaching source")
    return found[0] if found else None


def _policy(rules):
    cached = getattr(rules, "_feature_ability_lessons", None)
    if cached is not None:
        return cached
    path = Path(rules.root) / POLICY
    if not path.is_file():
        path = Path(__file__).resolve().parent.parent / POLICY
    data = json.loads(path.read_text(encoding="utf-8"))
    if (data.get("schema_version") != 1 or data.get("contract") != "permanent_tp_ability_lesson"
            or type(data.get('source_files'))is not dict):
        raise ValueError("unsupported Ability lesson policy")
    for relative, expected in data["source_files"].items():
        if hashlib.sha256((Path(rules.root) / relative).read_bytes()).hexdigest() != expected:
            raise ValueError("Ability lesson source changed: " + relative)
    rows = _vim_rules(rules,data.get('rules'),data['source_files'])
    for uid, row in rows.items():
        source = rules.selection.units[uid]["source"]
        bounds = row["lines"]
        lines = (Path(rules.root) / row["source_file"]).read_text(encoding="utf-8").splitlines()
        excerpt = "\n".join(lines[bounds[0]-1:bounds[1]])
        if ("input/" + source["file"] != row["source_file"] or source["lines"] != bounds
                or source["sha256"] != data["source_files"][row["source_file"]]
                or hashlib.sha256(excerpt.encode()).hexdigest() != row["excerpt_sha256"]
                or row["parent"] not in rules.selection.units
                or row["point_cost"] != 2 or type(row["once_per_pokemon"]) is not bool):
            raise ValueError("Ability lesson declaration changed: " + uid)
        for choice in row["abilities"]:
            unit = rules.selection.units.get(choice["id"], {})
            if (unit.get("title") != choice["title"]
                    or "input/" + unit.get("source", {}).get("file", "") != choice["source_file"]
                    or unit.get("source", {}).get("sha256") != data["source_files"][choice["source_file"]]):
                raise ValueError("Ability lesson choice binding changed: " + uid)
            if choice['id'] == 'ability/먹보':
                if uid != 'feat/요리-음미':raise ValueError('core Gluttony belongs to its actual Culinary Appreciation lesson')
                __import__('capacity_abilities').validate_core_gluttony(rules,rules.core_abilities[choice['id']])
    rules._feature_ability_lessons = rows
    return rows


def _qualify(engine, teacher, pupil, uid, ability):
    import pokemon_activities as ACTIVITIES
    WORLD.require_actors(engine, teacher, pupil)
    ACTIVITIES._trainer(teacher)
    ACTIVITIES._pokemon(pupil)
    ACTIVITIES._outside(engine)
    row = _policy(engine.r)[uid]
    if uid == 'feat/생기활발':
        import breather as BREATHER
        BREATHER.feature_receipt(engine,teacher,BREATHER.VIM)
    if uid == 'feat/래밍-스피드' and __import__('conquerors_march').acquired(teacher, uid) is None:
        raise ValueError('actual acquired Ramming Speed and Rider prerequisite required')
    TEACHING.source(engine.r, uid, row["parent"], TEACHING.POINTS)
    if not TEACHING._acquired_feature(teacher, uid) or not TEACHING._acquired_feature(teacher, row["parent"]):
        raise ValueError("actual acquired teaching Feature and parent class required")
    if row["own_pokemon"]:
        ACTIVITIES._owner(teacher, pupil)
    if teacher.spec.get("frequency_state", {}).get("day", 0) != pupil.spec.get("frequency_state", {}).get("day", 0):
        raise ValueError("teaching calendars must agree")
    effects, header = engine.r.feat_effects(uid)
    if effects != row["effects"] or header.get("frequency", {}).get("action") != "extended":
        raise ValueError("Ability lesson extracted declaration changed")
    selected = ABILITIES.ability_id(engine.r, ability)
    if selected not in {choice["id"] for choice in row["abilities"]}:
        raise ValueError("Ability is outside this Feature's explicit choices")
    if uid=='feat/생기활발' and engine.r._selected_rule('ability/생기')!=selected:
        raise ValueError('Vim uses the explicitly selected Vigor source, never an implicit homebrew choice')
    TEACHING.source(engine.r, selected)
    engine.r.selection.require_supported_version(selected)
    PAYMENTS.validate(pupil)
    payments = pupil.spec.get(GRANTS.KEY, {}).get("payments", {})
    if row["once_per_pokemon"] and any(receipt["acquisition"]["rule_id"] == uid for receipt in payments.values()):
        raise ValueError("Ability teaching Feature may target this Pokemon only once")
    if not row["once_per_pokemon"] and selected in ABILITIES.known(pupil):
        # No printed once-per-Pokemon limit; a Pokemon that already has the Ability cannot gain it again.
        raise ValueError("the target already has the printed Ability")
    if TEACHING._balance(pupil.spec) < row["point_cost"]:
        raise ValueError("Ability teaching requires two actual Tutor Points")
    return row, selected


def teach(engine, teacher, *, target, feature, ability, seconds, reason, connection_replace=None,advanced_connection=False):
    """Execute one explicit Extended lesson, paid once by its actual pupil."""
    uid = identity(engine.r, feature)
    if uid is None:
        raise ValueError("reviewed Ability teaching Feature required")
    CHECKS.integer(seconds, "GM-established Extended lesson duration", 1)
    TEACHING._text(reason, "Ability teaching duration and application reason")
    TEACHING._text(ability, "explicit Ability teaching choice")
    if connection_replace is not None and uid!='feat/생기활발':raise ValueError('this lesson has no Connection Move replacement')
    if type(advanced_connection)is not bool or (advanced_connection and uid!='feat/생기활발'):
        raise ValueError('this lesson has no immediate Connection choice')

    def apply(e, pupil, owner):
        row, selected = _qualify(e, owner, pupil, uid, ability)
        group_id = "ability-lesson:" + pupil.entity_id + ":" + uid
        source_id = group_id + ":ability"
        job_id = "training:" + group_id
        if not TURN.spend(e, owner, "extended", uid):
            raise ValueError("Ability teaching requires actual Extended action permission")
        JOBS.run_fixed(e, owner, (pupil,), seconds=seconds, source=uid, job_id=job_id,
                       context={"ability_id": selected, "payment_id": group_id, "reason": reason})
        # The clock can change a participant. Never pay or grant from stale
        # ownership, Feature, source, choice or balance observed before work.
        _, current = _qualify(e, owner, pupil, uid, ability)
        if current != selected:
            raise ValueError("Ability teaching choice changed during the lesson")
        def vim_connection(completed_engine, completed_pupil):
            GRANTS.state(completed_pupil)['sources'][source_id]['ability_lesson'] = {
                'teacher_id':owner.entity_id,'ability_id':selected,'job_id':job_id,
                'seconds':seconds,'completed_at':completed_engine.elapsed_seconds}
            import endure as ENDURE
            mid=ENDURE.learn_connection(completed_engine,completed_pupil,
                replace=connection_replace,advanced=advanced_connection,teacher=owner)
            GRANTS.state(completed_pupil)['sources'][source_id]['ability_lesson']['connection_move']=mid
        receipt = PAYMENTS.acquire(
            e, pupil, group_id, [{"source_id": source_id, "field": "abilities", "value": selected}],
            row["point_cost"], rule_id=uid, reason=reason, lifetime=None,
            _native_completion=vim_connection if uid=='feat/생기활발' else None,
        )
        if uid!='feat/생기활발':
            GRANTS.state(pupil)["sources"][source_id]["ability_lesson"] = {
                "teacher_id": owner.entity_id, "ability_id": selected,
                "job_id": job_id, "seconds": seconds, "completed_at": e.elapsed_seconds,
            }
        if selected == 'ability/먹보':
            __import__('food_effects').core_lesson_boundary(e,pupil,source_id)
        import trainer_retraining as RETRAINING
        RETRAINING.irreversible(e, owner, uid, event_id=job_id,
                               reason="completed permanent Ability lesson to " + pupil.entity_id + ": " + selected)
        e.log(pupil.name + " learned " + ABILITIES.label(e.r, selected) + " for 2 TP", uid)
        return {"activity": "teach_feature_ability", "source": uid, "ability": selected,
                "point_cost": row["point_cost"], "seconds": seconds, "job_id": job_id,
                "payment": receipt}

    return GRANTS.transition(engine, target, apply, participants=(teacher,))
