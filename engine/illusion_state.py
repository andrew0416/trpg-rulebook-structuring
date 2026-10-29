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
    known=revealed(row,observer) or __import__('oracle').sight(observer);mode=value['mode']
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


GENJUTSU_KEY='genjutsu_illusion'


def genjutsu_active(actor):
    row=actor.spec.get(GENJUTSU_KEY)
    return row if row and row['status']=='active' and __import__('ninja').acquired(actor,__import__('ninja').GENJUTSU) else None


def _genjutsu_sign(row):
    row=deepcopy(row);row.pop('fingerprint',None)
    row['fingerprint']=__import__('root_resolution').fingerprint(row)
    return row


def validate_genjutsu(engine,index):
    validate_ability_illusions(engine,index)
    import ninja as N
    for actor in index.values():
        row=actor.spec.get(GENJUTSU_KEY)
        if row is None:continue
        if type(row)is not dict or set(row)!={'source','actor_id','acquisition','appearance','darkness','stealth_rank','status','created_at','ended_at','end_reason','fingerprint'} or row!=_genjutsu_sign(row):raise ValueError('actual Genjutsu illusion evidence changed')
        if row['actor_id']!=actor.entity_id or row['source']!=N.GENJUTSU or not any(r['request_id']==row['acquisition'] for r in N.records(actor,N.GENJUTSU)):raise ValueError('actual acquired Genjutsu source required')
        if row['status'] not in ('active','broken') or type(row['darkness'])is not bool:raise ValueError('actual Genjutsu mode/lifecycle required')
        if row['darkness']!=(row['appearance'] is None):raise ValueError('exact darkness concealment or mundane object disguise required')
        if not row['darkness']:_text(row['appearance'],'mundane object appearance')
        import common_checks as C
        SKILL.validate_rank_value(engine.r,row['stealth_rank'],label='Genjutsu Stealth rank');C.integer(row['created_at'],'Genjutsu creation time',0,engine.elapsed_seconds)
        if row['status']=='broken':
            C.integer(row['ended_at'],'Genjutsu ending time',row['created_at'],engine.elapsed_seconds);_text(row['end_reason'],'Genjutsu ending')
        elif row['ended_at'] is not None or row['end_reason'] is not None:raise ValueError('active Genjutsu cannot have ending evidence')


def genjutsu(engine,creator,*,appearance=None,darkness=False):
    import ninja as N,scene_lighting as LIGHT
    N.require(engine,creator,N.GENJUTSU)
    if type(darkness)is not bool or darkness!=(appearance is None):raise ValueError('choose darkness concealment or one mundane object appearance')
    if darkness:
        if not LIGHT.active(engine) or tuple(creator.pos) in LIGHT.illuminated(engine)[0]:raise ValueError('Genjutsu darkness concealment requires actual darkness')
    else:_text(appearance,'mundane object appearance')
    def apply(staged,actor):
        if not TURN.spend(staged,actor,'standard',N.GENJUTSU):raise ValueError('Genjutsu requires Standard Action')
        # Pay first: creation does not break the illusion it is just creating.
        row={'source':N.GENJUTSU,'actor_id':actor.entity_id,'acquisition':N.acquired(actor,N.GENJUTSU)['request_id'],
            'appearance':appearance,'darkness':darkness,'stealth_rank':SKILL.rank(staged.r,actor,'은신')[2],
            'status':'active','created_at':staged.elapsed_seconds,'ended_at':None,'end_reason':None}
        actor.spec[GENJUTSU_KEY]=_genjutsu_sign(row)
        return deepcopy(actor.spec[GENJUTSU_KEY])
    return GRANTS.transition(engine,creator,apply)


def break_genjutsu(engine,actor,reason):
    row=genjutsu_active(actor)
    if row:
        row=dict(row,status='broken',ended_at=engine.elapsed_seconds,end_reason=reason)
        actor.spec[GENJUTSU_KEY]=_genjutsu_sign(row)


def interact_genjutsu(engine,observer,target,skill,*,interaction,reason,**check_options):
    WORLD.require_actors(engine,observer,target);_text(interaction,'observed direct interaction');_text(reason,'direct interaction reason')
    canonical=SKILL.skill_id(engine.r.skill_policy,skill,required=True)
    if observer is target or canonical not in ('occult education','intuition'):raise ValueError('another direct interactor uses Occult Education or Intuition')
    if not genjutsu_active(target):raise ValueError('active Genjutsu illusion required')
    def apply(staged,who,holder):
        row=genjutsu_active(holder);dc=10+SKILL.rank(staged.r,holder,'은신')[2]
        success,total=staged.skill_check(who,skill,dc,**check_options)
        result={'total':total,'passed':success}
        if success:break_genjutsu(staged,holder,'direct interaction: '+interaction+'; '+reason)
        return {'dc':dc,'success':success,'check':result,'interaction':interaction}
    return GRANTS.transition(engine,observer,apply,participants=(target,),include_rulings=True)


def genjutsu_sensory(engine,observer,target,value,chosen):
    if type(target)is dict:return None
    row=genjutsu_active(target)
    if row is None or observer is target:return None
    if __import__('oracle').sight(observer):return None
    if value['provider']=='aura' or value['mode'] in ('aura','aura_sight'):
        return 'absent','genjutsu_conceals_aura',{'presence':False} if 'presence' in chosen else {}
    if value['mode']!='visual':return None
    if row['darkness']:
        import scene_lighting as LIGHT
        if LIGHT.active(engine) and tuple(target.pos) not in LIGHT.illuminated(engine)[0]:
            return 'absent','genjutsu_darkness',{'presence':False} if 'presence' in chosen else {}
        return None
    values={field:True if field=='presence' else WORLD.effective_location(engine,target) if field=='position' else 'mundane_object' if field=='kind' else row['appearance'] if field in ('shape','text') else None for field in chosen}
    return 'observed','genjutsu_mundane_object',values


ABILITY_ILLUSION='ability_illusion_state'


def ability_illusion_active(actor):
    import ability_transitions as A,oracle as O
    row=actor.spec.get(ABILITY_ILLUSION)
    return row if row and row['active'] is not None and A.active(actor,O.ILLUSION) else None


def mark_appearance(engine,actor,target,*,forfeit=None):
    import oracle as O,ability_transitions as A
    WORLD.require_actors(engine,actor);uid=__import__('perception_observe')._actual(engine,actor,target)
    if not A.active(actor,O.ILLUSION):raise ValueError('actual active Illusion Ability required')
    maximum=SKILL.rank(engine.r,actor,'집중')[2]
    def apply(e,a):
        row=a.spec.setdefault(ABILITY_ILLUSION,{'marks':[],'active':None,'used_round':None,'history':[]})
        if uid in row['marks']:raise ValueError('Illusion target already marked')
        if forfeit is not None:
            if forfeit not in row['marks']:raise ValueError('forfeit an actual previous Illusion mark')
            row['marks'].remove(forfeit)
        if len(row['marks'])>=maximum:raise ValueError('forfeit an old mark before exceeding Focus Rank')
        if not TURN.spend(e,a,'standard',O.ILLUSION):raise ValueError('Illusion marking requires Standard Action')
        row['marks'].append(uid);row['history'].append({'kind':'mark','target_id':uid,'forfeit':forfeit,'at':e.elapsed_seconds})
        return deepcopy(row)
    return GRANTS.transition(engine,actor,apply)


def mimic_appearance(engine,actor,target,*,_release=False):
    import oracle as O,ability_transitions as A
    WORLD.require_actors(engine,actor);uid=__import__('perception_observe')._actual(engine,actor,target)
    if not A.active(actor,O.ILLUSION):raise ValueError('actual active Illusion Ability required')
    row=actor.spec.get(ABILITY_ILLUSION)
    if row is None or uid not in row['marks']:raise ValueError('actual marked target required')
    if row['used_round']==engine.round_no:raise ValueError('Illusion appearance used this round')
    def apply(e,a):
        subject=WORLD.entity_index(e)[uid];data=subject if type(subject)is dict else subject.spec
        image={k:deepcopy(data.get(k)) for k in ('name','species','size','shape','color','gender','appearance')}
        row=a.spec[ABILITY_ILLUSION]
        # This Free Action is also legal on the actual Pokeball release boundary.
        import action_lifecycle as ACTION
        if _release:ACTION.record_action(e,a,'free')
        elif not TURN.spend(e,a,'free',O.ILLUSION):raise ValueError('Illusion requires Free Action')
        row.update(active={'target_id':uid,'appearance':image,'vague_sounds':True,'intelligible_speech':False},used_round=e.round_no)
        row['history'].append({'kind':'mimic','target_id':uid,'round':e.round_no,'at':e.elapsed_seconds})
        return deepcopy(row['active'])
    return GRANTS.transition(engine,actor,apply)


def choose_release_appearance(engine,actor,target):
    WORLD.require_actors(engine,actor)
    uid=__import__('perception_observe')._actual(engine,actor,target)
    if uid not in actor.spec.get(ABILITY_ILLUSION,{}).get('marks',[]):raise ValueError('actual marked release appearance required')
    actor.spec['illusion_release_choice']=uid
    return uid


def on_release(engine,actor):
    uid=actor.spec.get('illusion_release_choice')
    if uid is None:return
    if not actor.on_field:raise ValueError('actual Pokeball release required')
    mimic_appearance(engine,actor,WORLD.entity_index(engine)[uid],_release=True)
    actor.spec.pop('illusion_release_choice',None)


def end_ability_illusion(engine,actor,reason):
    row=actor.spec.get(ABILITY_ILLUSION)
    if row and row['active'] is not None:
        row['history'].append({'kind':'end','reason':reason,'at':engine.elapsed_seconds});row['active']=None


def dismiss_ability_illusion(engine,actor):
    import oracle as O
    WORLD.require_actors(engine,actor)
    if ability_illusion_active(actor)is None:raise ValueError('actual active Illusion required')
    def apply(e,a):
        if not TURN.spend(e,a,'free',O.ILLUSION):raise ValueError('Illusion dismissal requires Free Action')
        end_ability_illusion(e,a,'Free dismissal')
    return GRANTS.transition(engine,actor,apply)


def ability_illusion_sensory(engine,observer,target,value,chosen):
    if type(target)is dict or observer is target or __import__('oracle').sight(observer):return None
    row=ability_illusion_active(target)
    if row is None:return None
    if value['mode']=='auditory':
        return 'observed','illusion_vague_sounds',{'presence':True} if 'presence' in chosen else {k:None for k in chosen}
    if value['mode']!='visual':return None
    image=row['active']['appearance'];values={}
    for field in chosen:
        values[field]=True if field=='presence' else WORLD.effective_location(engine,target) if field=='position' else None if field in ('identity','types','nature') else image.get(field)
    return 'observed','ability_illusion_appearance',values


def validate_ability_illusions(engine,index):
    for actor in index.values():
        row=actor.spec.get(ABILITY_ILLUSION)
        if row is None:continue
        if set(row)!={'marks','active','used_round','history'} or type(row['marks'])is not list or len(set(row['marks']))!=len(row['marks']):raise ValueError('actual distinct Illusion marks required')
        entities=WORLD.entity_index(engine)
        if not set(row['marks'])<=set(entities):raise ValueError('Illusion marks must resolve to actual objects or actors')
        if row['active'] is not None:
            if row['active']['target_id'] not in row['marks'] and not any(v.get('target_id')==row['active']['target_id'] and v['kind']=='mimic' for v in row['history']):raise ValueError('Illusion appearance needs an actual marked acquisition')
            if row['active']['vague_sounds']is not True or row['active']['intelligible_speech']is not False:raise ValueError('Illusion cannot produce intelligible speech')
