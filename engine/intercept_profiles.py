"""Selected Defender acquisition changes only its owner's Intercept cost.

The native defense producer seals this JSON profile in its attempt. Live
admission checks actual acquisition; historical validation checks the recorded
acquisition proof without demanding that the feature remain owned forever.
"""
from copy import deepcopy
import csv
import hashlib
import json
from pathlib import Path

import acquired_features as ACQUIRED
import skill_modifiers as SKILL

DEFENDER='feat/디펜더'
CLAUSE='C2CSV/input/db/feats.csv:R37:main'
POLICY='data/intercept-profiles-policy.json'
RECEIPTS='_feature_stat_receipts'
ALIASES=(DEFENDER,'디펜더')
MANEUVERS=('maneuver/근접-가로채기','maneuver/원거리-가로채기')


import resolution_transaction as _FINGERPRINTS

def identity(value):
    return DEFENDER if value in ALIASES else None


def _policy(rules):
    # No mutable Rules cache: source fingerprint/restore keeps its existing
    # ownership, and the baseline Full path does not read this source policy.
    value=json.loads((Path(rules.root)/POLICY).read_text(encoding='utf-8'))
    if (value.get('version')!=1 or value.get('source_id')!=DEFENDER
            or value.get('clause_id')!=CLAUSE
            or value.get('profile')!={'action':'shift','payment':'next','budget':{'shift':1}}
            or value.get('acquisition')!={'kind':'trainer','stat':'hp','delta':1,
                'prerequisite_skill':'육상','minimum_rank':4}):
        raise ValueError('exact reviewed Defender profile policy required')
    for relative,digest in value['source_files'].items():
        if hashlib.sha256((Path(rules.root)/relative).read_bytes()).hexdigest()!=digest:
            raise ValueError('Defender source changed: '+relative)
    with (Path(rules.root)/'input/db/feats.csv').open(encoding='utf-8-sig',newline='') as stream:
        row=next(row for number,row in enumerate(csv.reader(stream),1) if number==37)
    digest=_FINGERPRINTS.json_fingerprint(row, sort_keys=False, compact=True, allow_nan=True)
    anchor=value['chapter'];lines=(Path(rules.root)/anchor['file']).read_text(encoding='utf-8-sig').splitlines()
    excerpt='\n'.join(lines[anchor['start']-1:anchor['end']])
    if (row!=value['source_cells'] or digest!=value['source_row_sha256']
            or hashlib.sha256(excerpt.encode()).hexdigest()!=anchor['excerpt_sha256']):
        raise ValueError('Defender exact source row or chapter changed')
    if rules._selected_rule(DEFENDER)!=DEFENDER:
        raise ValueError('selected Defender edition needs its own cost policy')
    return value


def _acquired(actor):
    names=actor.spec.get('feats',[])
    if not isinstance(names,(list,tuple)):raise ValueError('actual Defender acquisition list required')
    matches=[name for name in names if identity(name)]
    if not matches:return None
    if actor.kind!='trainer' or len(matches)!=1:
        raise ValueError('Defender requires exactly one trainer acquisition')
    # Reuse native duplicate/rank/branch validation. The CSV clause is source
    # evidence; the selected native feature is the actual acquisition identity.
    ACQUIRED.validate_class_slots(actor)
    source=DEFENDER
    if actor.r._selected_rule(source)!=source:
        raise ValueError('selected Defender acquisition source changed')
    return source


def _stat_plan(actor,source):
    choices=actor.spec.get('feature_stat_imports',{})
    choice=choices.get(source) if isinstance(choices,dict) else None
    if (not isinstance(choice,dict) or set(choice)!={'mode','base_stat'}
            or choice['mode'] not in ('apply','included')
            or type(choice['base_stat']) is not int or choice['base_stat']<1):
        raise ValueError('Defender +HP requires explicit apply or included stat import')
    base=choice['base_stat']
    expected={'source':source,'stat':'hp','delta':1,'before':base,'after':base+1,'mode':choice['mode']}
    receipts=actor.custom_conditions.get(RECEIPTS,{})
    if not isinstance(receipts,dict):raise ValueError('feature stat receipt mapping required')
    if any(identity(key) and key!=source for key in receipts):
        raise ValueError('Defender acquisition source changed without reconciliation')
    old=receipts.get(source)
    if old is None:
        rank=SKILL.rank(actor.r,actor,'육상')[2]
        if rank<4:raise ValueError('Defender acquisition requires Adept Athletics')
        qualification={'skill':'athletics','minimum':4,'rank_at_acquisition':rank}
    else:
        qualification=old.get('qualification') if isinstance(old,dict) else None
        if (type(qualification)is not dict or set(qualification)!={'skill','minimum','rank_at_acquisition'}
                or qualification['skill']!='athletics' or type(qualification['minimum'])is not int
                or qualification['minimum']!=4 or type(qualification['rank_at_acquisition'])is not int
                or qualification['rank_at_acquisition']<4
                or qualification['rank_at_acquisition'] not in {
                    row['rank'] for row in SKILL._declared_ranks(actor.r)[0].values()}):
            raise ValueError('Defender acquisition qualification receipt changed')
    expected['qualification']=qualification
    if old is not None and old!=expected:
        raise ValueError('Defender +HP acquisition receipt changed')
    if old is None:
        current=base+1 if choice['mode']=='included' else base
        if actor.stats.get('hp')!=current or actor.spec['stats'].get('hp')!=current:
            raise ValueError('Defender stat import differs from actual base-sheet HP')
    return expected,old is None


def preflight_owned(engine,actor):
    source=_acquired(actor)
    if source is None:return None
    _policy(engine.r)
    receipt,missing=_stat_plan(actor,source)
    return source,receipt,missing


def register_owned(engine,actor,name):
    if identity(name) is None:return False
    plan=preflight_owned(engine,actor)
    if plan is None:raise ValueError('actual acquired Defender source required')
    source,receipt,missing=plan
    if missing:
        if receipt['mode']=='apply':
            actor.stats['hp']=receipt['after'];actor.spec['stats']['hp']=receipt['after']
        actor.custom_conditions.setdefault(RECEIPTS,{})[source]=deepcopy(receipt)
    engine.log('    '+actor.name+': Defender native Intercept Shift profile',source)
    return True


def profile(engine,reactor,event,maneuver_source):
    stance=__import__('commander_orders').sentinel_profile(engine,reactor)
    if stance is not None:return stance
    if maneuver_source not in MANEUVERS:raise ValueError('exact native Intercept maneuver required')
    plan=preflight_owned(engine,reactor)
    if plan is None:return {'action':'full','payment':'next','budget':{'standard':1,'shift':1},'modifier_sources':[]}
    source,receipt,missing=plan
    if missing:raise ValueError('Defender must have its actual registered acquisition receipt')
    return {'action':'shift','payment':'next','budget':{'shift':1},'modifier_sources':[{
        'source_id':source,'clause_id':CLAUSE,'actor_id':reactor.entity_id,
        'acquisition':deepcopy(receipt)}]}


def validate_profile(engine,actor,value,*,historical=True):
    if __import__('commander_orders').validate_sentinel_profile(engine,actor,value,historical=historical):return True
    if type(value)is not dict or set(value)!={'action','payment','budget','modifier_sources'}:
        raise ValueError('exact native Intercept cost profile required')
    if value=={'action':'full','payment':'next','budget':{'standard':1,'shift':1},'modifier_sources':[]}:
        if not historical and _acquired(actor) is not None:
            raise ValueError('actual Defender cannot silently use an unmodified Full profile')
        return True
    _policy(engine.r)
    sources=value['modifier_sources']
    if (value['action']!='shift' or value['payment']!='next' or value['budget']!={'shift':1}
            or type(sources)is not list or len(sources)!=1):
        raise ValueError('unsupported Defender Intercept profile')
    proof=sources[0]
    if (type(proof)is not dict or set(proof)!={'source_id','clause_id','actor_id','acquisition'}
            or proof['source_id']!=DEFENDER or proof['clause_id']!=CLAUSE
            or proof['actor_id']!=actor.entity_id or actor.kind!='trainer'):
        raise ValueError('Defender profile source owner changed')
    receipt=proof['acquisition'];source=proof['source_id']
    prereq=receipt.get('qualification') if isinstance(receipt,dict) else None
    if (type(receipt)is not dict or set(receipt)!={'source','stat','delta','before','after','mode','qualification'}
            or receipt['source']!=source or receipt['stat']!='hp' or type(receipt['delta'])is not int
            or receipt['delta']!=1 or type(receipt['before'])is not int or receipt['before']<1
            or type(receipt['after'])is not int or receipt['after']!=receipt['before']+1
            or receipt['mode'] not in ('apply','included')
            or type(prereq)is not dict or set(prereq)!={'skill','minimum','rank_at_acquisition'}
            or prereq['skill']!='athletics' or type(prereq['minimum'])is not int or prereq['minimum']!=4
            or type(prereq['rank_at_acquisition'])is not int or prereq['rank_at_acquisition']<4
            or prereq['rank_at_acquisition'] not in {
                row['rank'] for row in SKILL._declared_ranks(engine.r)[0].values()}):
        raise ValueError('Defender profile acquisition or prerequisite evidence changed')
    if actor.custom_conditions.get(RECEIPTS,{}).get(source)!=receipt:
        raise ValueError('Defender profile has no matching persisted acquisition receipt')
    if not historical:
        current=preflight_owned(engine,actor)
        if current is None or current[0]!=source or current[2] or current[1]!=receipt:
            raise ValueError('Defender profile differs from actual live acquisition')
    return True

