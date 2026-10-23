"""Iron Mind is a qualified acquired Edge consuming actual read attempts."""
from pathlib import Path
import json
import acquisition_qualification as Q
import world_entities as W
from source_context import verified_source

SOURCE='edge/강철의-정신'
NAMES=(SOURCE,'강철의 정신','Iron Mind')


def policy(rules):
    value=json.loads((Path(rules.root)/'data/iron-mind-policy.json').read_text(encoding='utf-8'))
    if value['rule_id']!=SOURCE or rules._selected_rule(SOURCE)!=SOURCE:raise ValueError('selected native Iron Mind source required')
    verified_source(rules,value['source'],label='Iron Mind')
    verified_source(rules,value['csv_source'],label='Iron Mind duplicate CSV')
    source=rules.selection.units[SOURCE]['source']
    if source.get('file')!=value['source']['file'].removeprefix('input/') or source.get('lines')!=value['lines']:raise ValueError('Iron Mind literal source identity changed')
    return value


def validate(actor):
    entries=actor.spec.get('edges',[])
    if type(entries) not in (list,tuple):raise ValueError('actual acquired Edge list required')
    if not any(value in NAMES for value in entries):return False
    return Q.owned_skill_edge(actor,SOURCE,policy(actor.r),prerequisite_reason='Iron Mind requires Novice Focus')


def notice(engine,reader,target,operation):
    W.require_actors(engine,reader,target)
    if operation!='read' or not validate(target):return None
    return {'source':SOURCE,'recipient_id':target.entity_id,'kind':'telepathy_read_attempt',
            'reader_id':reader.entity_id,'at':engine.elapsed_seconds}


def information(rules,notice):
    # Actual producer identities remain in the common signed evidence. This Edge
    # grants awareness of an attempt, not a reader's identity or the read result.
    return {field:notice[field] for field in policy(rules)['notice_information']}
