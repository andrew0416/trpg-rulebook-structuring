"""Native Illusionist-capability objects and their action/sense lifecycle."""
from copy import deepcopy
from math import isfinite

import skill_modifiers as SKILL
import state_grants as GRANTS
import turn as TURN
import world_entities as WORLD

SOURCE='capability/환영술사'
KIND='illusion'
PIERCING_SOURCES={'feat/정체밝힘-시야'}


def _text(value,label):
    if not isinstance(value,str) or not value.strip():raise ValueError(label+' must be nonempty text')
    return value


def _owner(engine,actor):
    WORLD.require_actors(engine,actor)
    if actor.kind!='pokemon':raise ValueError('Illusionist requires an actual Pokemon owner')
    if engine.r._selected_rule(SOURCE)!=SOURCE:raise ValueError('selected Illusionist capability required')
    names={SKILL.key(name) for name in GRANTS.effective_capabilities(actor)}
    if SKILL.key('환영술사') not in names and SKILL.key(SOURCE) not in names:
        raise ValueError('current Illusionist capability required')
    return actor


def _location(value):
    import state_fields as F
    result=F.location(value)
    if result['kind']!='grid':raise ValueError('Illusionist needs an explicit grid location')
    return result


def _distance(a,b):
    if a.get('map_id')!=b.get('map_id'):raise ValueError('Illusionist and illusion must share one map')
    return max(abs(a['cell'][0]-b['cell'][0]),abs(a['cell'][1]-b['cell'][1]))


def _dimensions(value):
    if not isinstance(value,dict) or set(value)!= {'length','width','height'}:raise ValueError('three explicit illusion dimensions required')
    result={}
    for key,item in value.items():
        if type(item) not in (int,float) or not isfinite(item) or item<=0 or item>50:
            raise ValueError('each illusion dimension must be at most 50 cm')
        result[key]=item
    return result


def _range(engine,creator,location):
    origin=_location(WORLD.effective_location(engine,creator));destination=_location(location)
    limit=SKILL.effective_rank(engine.r,creator,'집중')
    if _distance(origin,destination)>limit:raise ValueError('illusion exceeds the creator Focus-rank range')
    return origin,limit


def validate_record(engine,row,index,registry,policy):
    creator=index.get(row.get('creator_id'))
    if creator is None or creator.kind!='pokemon':raise ValueError('illusion creator must resolve to an actual Pokemon')
    _dimensions(row.get('dimensions_cm'));_text(row.get('appearance'),'illusion appearance')
    if row.get('complexity') not in ('simple','complex'):raise ValueError('illusion manipulation complexity must be simple or complex')
    if row.get('status') not in ('active','marred','dismissed'):raise ValueError('unknown illusion lifecycle status')
    import state_fields as F
    F.integer(row.get('created_at'),'illusion creation time',0,engine.elapsed_seconds)
    F.integer(row.get('last_manipulated_at'),'illusion manipulation time',0,engine.elapsed_seconds)
    F.integer(row.get('focus_rank_limit'),'recorded Focus rank',0)
    anchor=_location(row.get('anchor_location'))
    if row['status']!='dismissed' and _distance(anchor,_location(row.get('location')))>row['focus_rank_limit']:
        raise ValueError('illusion location exceeds its certified Focus-rank action range')
    reveals=row.get('revealed_to')
    if not isinstance(reveals,list):raise ValueError('illusion reveal ledger must be a list')
    seen=set()
    for reveal in reveals:
        if not isinstance(reveal,dict) or set(reveal)!= {'observer_id','method','source','at'}:raise ValueError('complete illusion reveal evidence required')
        observer=index.get(reveal['observer_id'])
        if observer is None:raise ValueError('illusion reveal observer must be an actual actor')
        if reveal['observer_id'] in seen:raise ValueError('one current reveal record per observer required')
        seen.add(reveal['observer_id'])
        if reveal['method'] not in ('touch','pierce'):raise ValueError('illusion reveal method must be touch or pierce')
        if reveal['method']=='touch' and reveal['source']!='physical/contact':raise ValueError('physical reveal source changed')
        if reveal['method']=='pierce' and reveal['source'] not in PIERCING_SOURCES:raise ValueError('supported actual illusion-piercing source required')
        F.integer(reveal['at'],'illusion reveal time',0,engine.elapsed_seconds)
    if row['status']=='active' and any(x['method']=='touch' for x in reveals):raise ValueError('physically disturbed illusion must be visibly marred')
    return {'visual_only':True,'physical':False,'status':row['status'],'creator_id':creator.entity_id,
        'maximum_dimension_cm':50,'focus_range_m':row['focus_rank_limit'],'revealed_to':sorted(seen),
        'lifetime':'creator_dismissal','restorable':True,'unresolved':[]}


def _commit(engine,creator,row,cost,reason):
    import special_entities as SPECIAL
    # Validate every fallible source/state condition before staging the action spend.
    proposed=deepcopy(row);proposed.update(source_profile=engine.r.ruleset.name,source_ids=[SOURCE],provenance={'source':'gm/observation','reason':reason})
    registry=dict(getattr(engine,'_physical_objects',{}));registry[row['id']]=proposed
    SPECIAL.validate_record(engine,proposed,registry)
    def apply(staged,owner):
        if cost is not None and not TURN.spend(staged,owner,cost,SOURCE):raise ValueError('required Illusionist action is unavailable')
        return SPECIAL.observe(staged,row,reason=reason)
    return GRANTS.transition(engine,creator,apply)


def create(engine,creator,illusion_id,*,location,dimensions_cm,appearance,reason):
    creator=_owner(engine,creator);_text(illusion_id,'illusion identity');_text(appearance,'illusion appearance');_text(reason,'illusion reason')
    if illusion_id in WORLD.entity_index(engine):raise ValueError('illusion identity already exists')
    location=_location(location);origin,limit=_range(engine,creator,location)
    row={'id':illusion_id,'kind':KIND,'location':location,'creator_id':creator.entity_id,
        'dimensions_cm':_dimensions(dimensions_cm),'appearance':appearance,'complexity':'simple',
        'created_at':engine.elapsed_seconds,'last_manipulated_at':engine.elapsed_seconds,
        'anchor_location':origin,'focus_rank_limit':limit,'status':'active','revealed_to':[]}
    return _commit(engine,creator,row,'standard',reason)


def manipulate(engine,creator,illusion_id,*,location,appearance,complexity,reason):
    creator=_owner(engine,creator);_text(appearance,'illusion appearance');_text(reason,'illusion reason')
    if complexity not in ('simple','complex'):raise ValueError('simple or complex illusion manipulation required')
    current=getattr(engine,'_physical_objects',{}).get(illusion_id)
    if not isinstance(current,dict) or current.get('kind')!=KIND:raise ValueError('actual illusion identity required')
    if current['creator_id']!=creator.entity_id or current['status']=='dismissed':raise ValueError('only the active illusion creator may manipulate it')
    location=_location(location);origin,limit=_range(engine,creator,location);row=deepcopy(current)
    row.update(location=location,appearance=appearance,complexity=complexity,last_manipulated_at=engine.elapsed_seconds,anchor_location=origin,focus_rank_limit=limit)
    return _commit(engine,creator,row,'swift' if complexity=='simple' else 'standard',reason)


def _piercing(engine,observer,source):
    if source not in PIERCING_SOURCES or engine.r._selected_rule(source)!=source:raise ValueError('selected illusion-piercing source required')
    import contest_features as FEATURES
    if not FEATURES.owned(observer,source):raise ValueError('current acquired illusion-piercing source required')


def reveal(engine,observer,illusion_id,*,method,source=None,reason):
    WORLD.require_actors(engine,observer);_text(reason,'illusion reveal reason')
    current=getattr(engine,'_physical_objects',{}).get(illusion_id)
    if not isinstance(current,dict) or current.get('kind')!=KIND or current.get('status')=='dismissed':raise ValueError('active illusion identity required')
    row=deepcopy(current)
    if method=='touch':
        if source not in (None,'physical/contact'):raise ValueError('touch reveal has physical contact provenance')
        here=_location(WORLD.effective_location(engine,observer));there=_location(row['location'])
        if _distance(here,there)>1:raise ValueError('physical contact requires adjacency')
        source='physical/contact';row['status']='marred'
    elif method=='pierce':_piercing(engine,observer,source)
    else:raise ValueError('illusion reveal method must be touch or pierce')
    record={'observer_id':observer.entity_id,'method':method,'source':source,'at':engine.elapsed_seconds}
    row['revealed_to']=[x for x in row['revealed_to'] if x['observer_id']!=observer.entity_id]+[record]
    creator=WORLD.actor_index(engine)[row['creator_id']]
    return _commit(engine,creator,row,None,reason)


def dismiss(engine,creator,illusion_id,*,reason):
    creator=_owner(engine,creator);_text(reason,'illusion dismissal reason')
    current=getattr(engine,'_physical_objects',{}).get(illusion_id)
    if not isinstance(current,dict) or current.get('kind')!=KIND or current.get('creator_id')!=creator.entity_id:raise ValueError('owned illusion identity required')
    if current['status']=='dismissed':raise ValueError('illusion is already dismissed')
    row=deepcopy(current);row['status']='dismissed';row['location']={'kind':'unknown'}
    return _commit(engine,creator,row,None,reason)


def revealed(row,observer):
    return row.get('status')=='marred' or any(x.get('observer_id')==observer.entity_id for x in row.get('revealed_to',()))


def sensory_result(engine,observer,row,value,chosen):
    """Project the image without leaking its physical-object identity."""
    if row.get('status')=='dismissed':return 'absent','illusion_dismissed',{'presence':False} if 'presence' in chosen else {}
    known=revealed(row,observer);mode=value['mode']
    if mode!='visual':
        if mode=='touch':return 'not_observable','physical_contact_requires_reveal_action',{}
        return 'absent','visual_only_illusion',{'presence':False} if 'presence' in chosen else {}
    values={}
    for field in chosen:
        if field=='presence':actual=True
        elif field=='position':actual=deepcopy(row['location'])
        elif field=='identity':actual=row['id'] if known else None
        elif field=='kind':actual=KIND if known else None
        elif field in ('text','shape','color','species','types','gender','nature','size'):actual=row['appearance'] if field in ('text','shape') else None
        else:actual=None
        values[field]=actual
    return 'observed','illusion_revealed' if known else 'visual_projection',values
