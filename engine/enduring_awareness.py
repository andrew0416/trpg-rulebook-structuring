"""Awareness: a live owner's passive bonus on every actual saving check.

Prerequisites are checked at acquisition, including GM classification of three
actually owned defensive abilities. Later check eligibility is not confused
with that historical acquisition evidence, and the trainer never gets +2.
"""
from copy import deepcopy
import skill_modifiers as S

AWARENESS='feat/자각'
AWARENESS_CSV='C2CSV/input/db/feats.csv:R128:main'
AWARENESS_ALIASES=('Awareness',AWARENESS_CSV)
ENDURING='class/불굴의-투지'

def _is(name,uid,aliases=()):
    return S.key(name) in {S.key(x) for x in (uid,uid.split('/')[-1].replace('-',' '),*aliases)}

def acquired(a,uid,aliases=()):
    names=[]
    for key in ('classes','feats'):
        values=a.spec.get(key,[])
        if not isinstance(values,(tuple,list)):raise ValueError('actual feature ownership lists required')
        names.extend(values)
    count=sum(_is(x,uid,aliases) for x in names)
    if count>1:raise ValueError('duplicate aliases are not additional feature acquisitions')
    return count==1

def awareness_source(actor):
    if not acquired(actor,AWARENESS,AWARENESS_ALIASES):return None
    return AWARENESS_CSV if AWARENESS_CSV in [*actor.spec.get('classes',[]),*actor.spec.get('feats',[])] else AWARENESS

def acquisition_record(trainer,source):
    record=trainer.spec.get('_awareness_acquisition')
    if not isinstance(record,dict) or record.get('trainer_id')!=trainer.entity_id or record.get('source')!=source:
        raise ValueError('Awareness requires confirmed source-specific acquisition prerequisites')
    return record

def _selected(e,uid):
    if e.r._selected_rule(uid)!=uid:raise ValueError('selected Awareness prerequisite variant needs its own source policy')

def roster(e):
    actors=[*getattr(e,'everyone',[]),*getattr(e,'_time_actors',[]),*getattr(getattr(e,'gm',None),'everyone',[])]
    actors=list({id(a):a for a in actors}.values())
    by_id={}
    for a in actors:
        uid=a.spec.get('id')
        if uid is not None:
            if not isinstance(uid,str) or not uid.strip():raise ValueError('nonempty actual actor identity required')
            if uid in by_id and by_id[uid] is not a:raise ValueError('ambiguous actor identities in Awareness roster')
            by_id[uid]=a
    return by_id

def confirm(e,trainer,defenders,*,reason):
    if not isinstance(reason,str) or not reason.strip():raise ValueError('explicit GM acquisition reason required')
    source=awareness_source(trainer)
    if trainer.kind!='trainer' or source is None or not acquired(trainer,ENDURING,('Enduring Soul',)):
        raise ValueError('actual Awareness and Enduring Soul acquisitions required')
    _selected(e,source);_selected(e,ENDURING)
    if min(S.effective_rank(e.r,trainer,k) for k in ('육상','집중'))<3:raise ValueError('Enduring Soul requires Novice Athletics and Focus at acquisition')
    actors=roster(e);tid=trainer.spec.get('id')
    if actors.get(tid) is not trainer:raise ValueError('registered trainer identity required')
    if not isinstance(defenders,(tuple,list)) or len(defenders)!=3:raise ValueError('three distinct owned Pokemon with defensive abilities required')
    checked=[]
    for row in defenders:
        if not isinstance(row,dict) or set(row)!={'pokemon','ability','defensive_reason'}:raise ValueError('actual Pokemon, defensive ability and GM classification reason required')
        p=row['pokemon'];ability=row['ability'];why=row['defensive_reason']
        if p.kind!='pokemon' or actors.get(p.spec.get('id')) is not p or p.spec.get('trainer_id')!=tid:raise ValueError('acquisition evidence must be an actual owned Pokemon')
        if not isinstance(ability,str) or not ability or not isinstance(why,str) or not why.strip():raise ValueError('GM classification of the actual defensive ability required')
        import ability_transitions as AB
        uid=AB.ability_id(e.r,ability);name=AB.label(e.r,uid)
        if uid not in {AB.ability_id(e.r,current) for current in p.abilities} or name not in e.r.ability_effects:
            raise ValueError('Pokemon does not have this actual sourced ability')
        _selected(e,uid)
        checked.append({'pokemon_id':p.spec['id'],'ability_id':uid,'defensive_reason':why})
    if len({row['pokemon_id'] for row in checked})!=3:raise ValueError('one Pokemon cannot fill several prerequisite slots')
    if trainer.spec.get('_awareness_acquisition') is not None:raise ValueError('Awareness acquisition already confirmed')
    record={'trainer_id':tid,'source':source,'prerequisite_source':ENDURING,'defenders':checked,'reason':reason}
    trainer.spec['_awareness_acquisition']=record
    e.gm._rec('자각 취득 전제 확인',None,record,reason,trainer)
    return deepcopy(record)

def bonus(e,actor):
    if actor.kind!='pokemon':return 0
    tid=actor.spec.get('trainer_id')
    if tid is None:return 0
    trainer=roster(e).get(tid)
    if trainer is None:return 0
    if trainer.kind!='trainer':raise ValueError('Pokemon owner identity does not name a trainer')
    source=awareness_source(trainer)
    if source is None:return 0
    _selected(e,source)
    acquisition_record(trainer,source)
    if trainer.dead or trainer.fainted or trainer.hp<=0:return 0
    return 2

def register_owned(e,actor,name):
    if not _is(name,AWARENESS,AWARENESS_ALIASES):return False
    source=awareness_source(actor)
    if actor.kind!='trainer' or source is None:raise ValueError('Awareness is a trainer feature')
    _selected(e,source)
    acquisition_record(actor,source)
    e.log('  '+actor.name+': 자각은 현재 소유 포켓몬의 실제 내성마다 적용',source)
    return True
