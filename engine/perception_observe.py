"""Source-bound sensing with finite information rights and actual world gates."""
from copy import deepcopy
from math import hypot,isfinite
import json
import common_checks as C,crafting_recipes as Q,state_grants as G,skill_modifiers as S,world_entities as W,resolution_transaction as TX

ENV='_sensory_environments'
THOUGHT='surface_thought_observation'
MODES=('visual','spatial','aura','mental','auditory','touch')
ENTITY_FIELDS=('presence','identity','position','kind','species','types','gender','nature','color','text','size','shape')
GEOMETRY_FIELDS=('species','size','shape','footprint','body_mode','appearance','height_m','destroyed','consumed')


def observe_blessing(engine, observer, gift, *, target=None, selection=None):
    """Route an acquired Gift through the shared source-bound observer."""
    import blessing_observations as B
    return B.observe(engine,observer,gift,target=target,selection=selection)


def record_blessing_fact(engine, observer, gift, value, *, reason, target=None):
    """Record the GM world fact consumed by a Blessing observation."""
    import blessing_observations as B
    return B.record_fact(engine,observer,gift,value,reason=reason,target=target)


def _names(values,*,empty=False):
    if type(values) is not list or not empty and not values or len(set(map(str,values)))!=len(values):raise ValueError('distinct sensory declaration values required')
    for value in values:Q._text(value)


def declaration(value):
    Q._fields(value,('id','source','capabilities','mode','range','path','medium','vision','provider','information','check'))
    Q._text(value['id']);Q._text(value['source']);_names(value['capabilities'],empty=True);_names(value['information']);_names(value['medium'],empty=True)
    if value['mode'] not in MODES or value['path'] is not None and value['path'] not in MODES or value['vision'] not in (None,'usable','clear'):raise ValueError('explicit supported sensory path and vision policy required')
    reach=value['range']
    if reach is not None:
        Q._fields(reach,('metric','maximum'))
        if reach['metric'] not in ('chebyshev','euclidean'):raise ValueError('explicit sensory distance metric required')
        maximum=reach['maximum']
        if type(maximum) is dict:
            Q._fields(maximum,('kind','skill','base','multiplier','rank_adjustment'))
            if maximum['kind']!='skill_rank':raise ValueError('supported actual skill range formula required')
            Q._text(maximum['skill']);C.integer(maximum['base'],'range base',0);C.integer(maximum['multiplier'],'range multiplier',1)
            adjustment=maximum['rank_adjustment']
            if adjustment is not None:
                Q._fields(adjustment,('source','parameter'));Q._text(adjustment['source']);Q._text(adjustment['parameter'])
        elif type(maximum) not in (int,float) or not isfinite(maximum) or maximum<0:raise ValueError('explicit finite sensory range in grid cells required')
    import aura_state as A,aura_pulse as P
    permitted={'entity':ENTITY_FIELDS,'aura':('presence',*A.FIELDS),'surface':('presence','surface_thought'),'psychic_residue':('presence','traces')}
    if value['provider'] not in permitted or not set(value['information'])<=set(permitted[value['provider']]):raise ValueError('requested sensory information has no supported source provider')
    if value['provider']=='aura' and value['source']!=A.SOURCE or value['provider']=='surface' and value['source']!=P.SOURCE:raise ValueError('native aura information retains its own selected source')
    check=value['check']
    if check is not None:
        Q._fields(check,('skill','dc','purpose'));Q._text(check['skill']);Q._text(check['purpose']);C.integer(check['dc'],'sensory check DC',0)
    return deepcopy(value)


def native(source,capabilities,*,provider='entity',information=('presence',),mode='mental'):
    return {'id':'native:'+source,'source':source,'capabilities':list(capabilities),'mode':mode,'range':None,'path':None,
        'medium':[],'vision':None,'provider':provider,'information':list(information),'check':None}


def traits(actor,*,engine=None):
    import capability_traits as T
    return T._projection(actor,engine=engine)


def range_maximum(actor,reach):
    maximum=reach['maximum']
    if type(maximum) is not dict:return maximum
    import arithmetic as A,capability_parameter_edges as P
    rank=S.effective_rank(actor.r,actor,maximum['skill']);bonus=0
    adjustment=maximum['rank_adjustment']
    if adjustment is not None:
        bonus=P.parameters(actor,adjustment['source']).get(adjustment['parameter'],0)
        C.integer(bonus,'actual range-only rank adjustment',0)
    return A.evaluate('(rank+bonus)*multiplier+base',dict(rank=rank,bonus=bonus,multiplier=maximum['multiplier'],base=maximum['base']))


def current_thought(actor):
    """One observed world fact; the consuming capability owns reading permission."""
    import aura_pulse as P
    legacy=P.validate(actor);row=actor.spec.get(THOUGHT)
    if row is None:return None if legacy is None else legacy['surface']
    Q._fields(row,('source','target_id','text','reason','revision','at','sha256'))
    if row['source']!='gm/surface_thought' or row['target_id']!=actor.entity_id or row['sha256']!=TX.request_fingerprint({k:v for k,v in row.items() if k!='sha256'}):raise ValueError('actual observed thought evidence changed')
    Q._text(row['text']);Q._text(row['reason']);C.integer(row['revision'],'thought revision',1);C.integer(row['at'],'thought observation time',0)
    if legacy is not None and legacy['surface']!=row:raise ValueError('legacy thought projection differs from the actual observation')
    return row


def observe_thought(engine,target,thought,*,reason):
    W.require_actors(engine,target);Q._text(thought);Q._text(reason)
    def apply(e,c):
        import aura_pulse as P
        old=current_thought(c)
        row={'source':'gm/surface_thought','target_id':c.entity_id,'text':thought,'reason':reason,
             'revision':1 if old is None else old['revision']+1,'at':e.elapsed_seconds}
        row['sha256']=TX.request_fingerprint(row);c.spec[THOUGHT]=row
        if P.KEY in c.spec:c.spec[P.KEY]['surface']=deepcopy(row)
        e.gm._rec('surface thought',old,row,reason,c);return deepcopy(row)
    return G.transition(engine,target,apply,include_rulings=True)


def _actual(engine,observer,target):
    W.require_actors(engine,observer);index=W.entity_index(engine)
    uid=target.get('entity_id',target.get('id')) if type(target) is dict else getattr(target,'entity_id',None)
    if index.get(uid) is not target:raise ValueError('actual registered sensory target required')
    return uid


def _geometry_context(target):
    data=target if type(target) is dict else target.spec
    # Signed request values deliberately exclude floats. A canonical JSON text
    # binds observed fractional dimensions and body ratios without weakening that
    # contract or rounding the actual world measurement.
    return json.dumps({k:data.get(k) for k in GEOMETRY_FIELDS},ensure_ascii=False,sort_keys=True,allow_nan=False,separators=(',',':'))


def _context(engine,observer,target,*,geometry=False):
    grid=getattr(engine,'grid',None)
    weather_state=getattr(engine,'_weather_state',None)
    # weather_state.state() lazily creates this pristine registry on first read; it is
    # not an observable environment change, so observations taken before it existed stay valid.
    if weather_state=={'version':1,'sequence':0,'active':None,'natural':None,'history':[]}:weather_state=None
    result={'observer_location':W.effective_location(engine,observer),'target_location':W.effective_location(engine,target),
        'weather':engine.weather,'weather_state':deepcopy(weather_state),
        'blocking_cells':sorted(getattr(grid,'blocking',()))}
    if geometry:result['target_geometry']=_geometry_context(target)
    return result


def _environment_facts(value):
    Q._fields(value,('paths','medium','present',*(('geometry',) if 'geometry' in value else ())))
    if type(value['paths']) is not dict or not set(value['paths'])<=set(MODES):raise ValueError('explicit sensory channels required')
    if any(v is not None and type(v) is not bool for v in value['paths'].values()) or value['present'] is not None and type(value['present']) is not bool:raise ValueError('sensory path and presence facts must be boolean or unknown')
    if value['medium'] is not None:Q._text(value['medium'])
    if 'geometry' in value:
        Q._fields(value['geometry'],('size','shape'))
        for item in value['geometry'].values():
            if item is not None:Q._text(item)
    return deepcopy(value)


def environment_key(observer_id,target_id):return TX.request_fingerprint([observer_id,target_id])


def observe_environment(engine,observer,target,*,paths,medium=None,present=None,geometry=None,reason):
    target_id=_actual(engine,observer,target);Q._text(reason)
    facts={'paths':paths,'medium':medium,'present':present}
    if geometry is not None:facts['geometry']=deepcopy(geometry)
    facts=_environment_facts(facts)
    def apply(e,c):
        subject=W.entity_index(e)[target_id];key=environment_key(c.entity_id,target_id);rows=getattr(e,ENV,{})
        old=rows.get(key);row={'observer_id':c.entity_id,'target_id':target_id,'source':'gm/sensory_environment',
            'revision':1 if old is None else old['revision']+1,'at':e.elapsed_seconds,'reason':reason,'facts':facts,
            'context':_context(e,c,subject,geometry='geometry' in facts)}
        row['sha256']=TX.request_fingerprint(row)
        rows[key]=row;setattr(e,ENV,rows);e.gm._rec('sensory environment',old,row,reason,c)
        return deepcopy(row)
    return G.transition(engine,observer,apply,include_rulings=True)


def validate_world(engine,index):
    __import__('oracle').validate_world(engine,index)
    for actor in index.values():
        validate_channel_fact(engine,actor)
        thought=current_thought(actor)
        if thought is not None and 'at' in thought:C.integer(thought['at'],'thought observation world time',0,engine.elapsed_seconds)
    rows=getattr(engine,ENV,{})
    if type(rows) is not dict:raise ValueError('sensory environment registry must be a mapping')
    if not rows:return
    entities=W.entity_index(engine)
    for key,row in rows.items():
        Q._fields(row,('observer_id','target_id','source','revision','at','reason','facts','context','sha256'))
        if row['sha256']!=TX.request_fingerprint({k:v for k,v in row.items() if k!='sha256'}):raise ValueError('sensory environment evidence changed')
        if row['source']!='gm/sensory_environment' or row['observer_id'] not in index or row['target_id'] not in entities or key!=environment_key(row['observer_id'],row['target_id']):raise ValueError('actual sensory environment relationship required')
        C.integer(row['revision'],'sensory environment revision',1);C.integer(row['at'],'observed sensory world time',0,engine.elapsed_seconds)
        Q._text(row['reason']);_environment_facts(row['facts'])
        geometry='geometry' in row['facts']
        Q._fields(row['context'],('observer_location','target_location','weather','weather_state','blocking_cells',*(('target_geometry',) if geometry else ())))
        if geometry:
            text=row['context']['target_geometry'];Q._text(text);binding=json.loads(text)
            Q._fields(binding,GEOMETRY_FIELDS)
            if text!=json.dumps(binding,ensure_ascii=False,sort_keys=True,allow_nan=False,separators=(',',':')):raise ValueError('canonical sensory geometry binding required')
        import state_fields as F
        F.location(row['context']['observer_location']);F.location(row['context']['target_location'])


def _result(value,status,reason,values=None):
    values={} if values is None else values;unknown=[key for key,val in values.items() if val is None]
    if status=='observed' and unknown:status='unknown' if len(unknown)==len(values) else 'partial'
    return {'source':value['source'],'mode':value['mode'],'status':status,'reason':reason,'values':deepcopy(values),'unknown_fields':unknown}


def route(engine,observer,target,value,*,information=None):
    value=declaration(value);uid=_actual(engine,observer,target);Q._selected(engine,value['source'])
    if value['provider']=='psychic_residue':__import__('psionic_sight').route(engine,observer,target,value)
    chosen=list(value['information']) if information is None else information;_names(chosen)
    if not set(chosen)<=set(value['information']):raise ValueError('information exceeds this actual sensing declaration')
    if value['mode']=='visual' and observer.spec.get('oracle_focus') is not None:return value,chosen,_result(value,'not_observable','mark_of_vision_eyes_closed')
    current={S.key(name) for name in G.effective_capabilities(observer)}
    if value['capabilities'] and not current.intersection(S.key(name) for name in value['capabilities']):raise ValueError('current declared sensing capability required')
    if value['mode']=='visual' and type(target) is not dict:
        blocked=__import__('invisibility_state').visual_block(engine,target,observer=observer)
        if blocked is not None:return value,chosen,_result(value,'unknown' if blocked=='invisibility_time_unknown' else 'not_observable',blocked)
    import aura_state as A,aura_pulse as P
    if value['provider'] in ('aura','surface'):
        required=('파동 감지','Aura Reader',A.SOURCE) if value['provider']=='aura' else ('파동술','Aura Pulse',P.SOURCE)
        if not current.intersection(S.key(name) for name in required):raise ValueError('current native aura capability required')
        if type(target) is dict or observer is target:raise ValueError('native aura requires another actual actor')
    reach=value['range']
    if reach is not None:
        locations=[W.effective_location(engine,c) for c in (observer,target)]
        if any(loc['kind']!='grid' for loc in locations) or locations[0].get('map_id')!=locations[1].get('map_id'):return value,chosen,_result(value,'unknown','distance_unknown')
        a,b=(loc['cell'] for loc in locations);delta=[abs(a[i]-b[i]) for i in (0,1)]
        distance=max(delta) if reach['metric']=='chebyshev' else hypot(*delta)
        if distance>range_maximum(observer,reach):return value,chosen,_result(value,'not_observable','out_of_range')
    env=getattr(engine,ENV,{}).get(environment_key(observer.entity_id,uid));facts=None
    if env is not None and env.get('sha256')!=TX.request_fingerprint({k:v for k,v in env.items() if k!='sha256'}):raise ValueError('sensory environment evidence changed')
    if env is not None and env['context']==_context(engine,observer,target,geometry='geometry' in env['facts']):facts=env['facts']
    if value['path'] is not None:
        path=None if facts is None else facts['paths'].get(value['path'])
        if path is None:return value,chosen,_result(value,'unknown','path_unknown')
        if not path:return value,chosen,_result(value,'not_observable','path_blocked')
    if value['medium']:
        medium=None if facts is None else facts['medium']
        if medium is None:return value,chosen,_result(value,'unknown','medium_unknown')
        if medium not in value['medium']:return value,chosen,_result(value,'not_observable','medium_blocked')
    if value['vision'] is not None:
        import survivalist_features as V
        if '_survivalist_environment' not in observer.spec:return value,chosen,_result(value,'unknown','lighting_unknown')
        kind,_=V.vision(engine,observer)
        if kind=='total' or value['vision']=='clear' and kind!='none':return value,chosen,_result(value,'not_observable','vision_blocked')
    if value['provider']=='entity' and set(chosen).intersection(('color','text')):
        senses=traits(observer,engine=engine)
        if 'color' in chosen and senses['color_discrimination'] is False or 'text' in chosen and senses['visual_reading'] is False:return value,chosen,_result(value,'not_observable','sensory_information_unavailable')
    if value['provider']=='surface':
        row=P.validate(target);permission=None if row is None else row['open_to'].get(observer.entity_id)
        if permission is None or not permission['allowed']:return value,chosen,_result(value,'not_observable','mind_not_open')
    if value['path'] is not None or value['medium']:
        if facts is None or facts['present'] is None:return value,chosen,_result(value,'unknown','presence_unknown')
        if facts['present'] is False:return value,chosen,_result(value,'absent','no_detectable_presence',{'presence':False} if 'presence' in chosen else {})
    return value,chosen,None


def _values(engine,observer,target,value,chosen):
    if value['provider']=='psychic_residue':return _result(value,'observed','permitted_information',__import__('psionic_sight').values(engine,observer,target,chosen))
    disguised=__import__('illusion_state').ability_illusion_sensory(engine,observer,target,value,chosen)
    if disguised is not None:return _result(value,*disguised)
    disguised=__import__('illusion_state').genjutsu_sensory(engine,observer,target,value,chosen)
    if disguised is not None:return _result(value,*disguised)
    if value['provider']=='aura':
        import aura_state as A
        row=A.validate(target)
        if getattr(target,'dead',False) or row is not None and not row['living']:return _result(value,'absent','no_living_aura',{'presence':False} if 'presence' in chosen else {})
        if row is None:return _result(value,'unknown','aura_unknown',{field:None for field in chosen})
        if row['at']>engine.elapsed_seconds:raise ValueError('aura observation is from a future world time')
        values={field:True if field=='presence' else row[field] for field in chosen}
    elif value['provider']=='surface':
        surface=current_thought(target)
        values={field:True if field=='presence' else None if surface is None else surface['text'] for field in chosen}
    else:
        if type(target) is dict and target.get('kind')=='illusion':
            import illusion_state as ILLUSION
            status,reason,values=ILLUSION.sensory_result(engine,observer,target,value,chosen)
            return _result(value,status,reason,values)
        data=target if type(target) is dict else target.spec;values={}
        for field in chosen:
            if field=='presence':actual=True
            elif field=='identity':actual=data.get('entity_id',data.get('id'))
            elif field=='position':
                actual=W.effective_location(engine,target)
                if actual['kind']=='unknown':actual=None
            elif field=='kind':actual=data.get('kind') if type(target) is dict else target.kind
            elif field=='types':actual=data.get('types') if type(target) is dict else list(target.types)
            elif field in ('size','shape'):
                row=getattr(engine,ENV,{}).get(environment_key(observer.entity_id,_actual(engine,observer,target)))
                current=row is not None and row['context']==_context(engine,observer,target,geometry='geometry' in row['facts'])
                actual=row['facts'].get('geometry',{}).get(field) if current else None
            else:actual=data.get(field)
            values[field]=deepcopy(actual)
    return _result(value,'observed','permitted_information',values)


def observe(engine,observer,target,value,*,information=None,roll_options=None):
    value,chosen,blocked=route(engine,observer,target,value,information=information)
    if blocked is not None:return blocked
    if value['check'] is None:
        if roll_options:raise ValueError('passive sensing has no declared skill roll')
        if value['provider']=='psychic_residue':
            def apply(e,c,other):
                _,_,blocked=route(e,c,other,value,information=chosen)
                return blocked if blocked is not None else _values(e,c,other,value,chosen)
            return G.transition(engine,observer,apply,participants=(target,))
        result=_values(engine,observer,target,value,chosen)
        import optional_physical_equipment as OPTIONAL_EQUIPMENT
        return OPTIONAL_EQUIPMENT.reveal_observation(engine,observer,target,result)
    if type(target) is dict:raise ValueError('native scoped sensing check requires an actor target')
    import roll_context as RC
    options={} if roll_options is None else deepcopy(roll_options);check=value['check']
    if type(options) is not dict:raise ValueError('native sensory roll options must be a mapping')
    RC.plan(engine,observer,check['skill'],purpose=check['purpose'],target=target,**options)
    def apply(e,c,other):
        _,_,blocked=route(e,c,other,value,information=chosen)
        if blocked is not None:return blocked
        travel_bonus=__import__('chronicler').environment_perception_bonus(e,c,check['skill'])
        if travel_bonus:
            options['mods']=options.get('mods',0)+travel_bonus
            e.log('  스킬 보너스 '+__import__('chronicler').CLASS+': Travel Archive present place +'+str(travel_bonus),__import__('chronicler').CLASS)
        result=__import__('skill_feature_actions').resolve_check(e,c,check['skill'],check['dc'],e.skill_roll(c,check['skill'],skill_target=other,**options),options)
        sensed=_values(e,c,other,value,chosen) if result.passed else _result(value,'not_observable','check_failed')
        import optional_physical_equipment as OPTIONAL_EQUIPMENT
        sensed=OPTIONAL_EQUIPMENT.reveal_observation(e,c,other,sensed)
        sensed['check']={'passed':result.passed,'total':result.total,'dc':check['dc']}
        return sensed
    return G.transition(engine,observer,apply,participants=(target,))



CHANNEL_FACT='channel_information_observation'


def _channel_context(engine,subject):
    context={'location':W.effective_location(engine,subject),'conditions':sorted(subject.conditions),'capabilities':sorted(G.effective_capabilities(subject))}
    if subject.spec.get('oracle_focus') is not None:context['eyes_closed_for_mark']=True
    return context


def validate_channel_fact(engine,subject):
    row=subject.spec.get(CHANNEL_FACT)
    if row is None:return None
    Q._fields(row,('subject_id','at','reason','intentions','emotions','motivations','memories','senses','context','sha256'))
    if row['subject_id']!=subject.entity_id or row['sha256']!=TX.request_fingerprint({k:v for k,v in row.items() if k!='sha256'}):raise ValueError('Channel information observation identity changed')
    C.integer(row['at'],'Channel information observation time',0,engine.elapsed_seconds);Q._text(row['reason'])
    for name in ('intentions','emotions','motivations'):
        if row[name] is not None:Q._text(row[name])
    if row['memories'] is not None:
        if type(row['memories'])is not list:raise ValueError('observed past events must be explicit or unknown')
        for event in row['memories']:
            Q._fields(event,('at','text'));C.integer(event['at'],'observed memory event time',0,row['at']);Q._text(event['text'])
    if row['senses'] is not None:
        if type(row['senses'])is not dict or set(row['senses'])-set(MODES):raise ValueError('observed supported sensory channels required')
        for value in row['senses'].values():
            if value is not None:Q._text(value)
    return row


def observe_channel_information(engine,subject,*,intentions=None,emotions=None,motivations=None,memories=None,senses=None,reason):
    W.require_actors(engine,subject);Q._text(reason)
    def apply(e,c):
        row={'subject_id':c.entity_id,'at':e.elapsed_seconds,'reason':reason,'intentions':intentions,'emotions':emotions,
            'motivations':motivations,'memories':deepcopy(memories),'senses':deepcopy(senses),'context':_channel_context(e,c)}
        row['sha256']=TX.request_fingerprint(row);old=c.spec.get(CHANNEL_FACT);c.spec[CHANNEL_FACT]=row
        validate_channel_fact(e,c);e.gm._rec('observed Channel information',old,deepcopy(row),reason,c);return deepcopy(row)
    return G.transition(engine,subject,apply)


def channel_information(engine,subject,*,sensory=False):
    W.require_actors(engine,subject);row=validate_channel_fact(engine,subject)
    if sensory:
        current=row is not None and row['context']==_channel_context(engine,subject)
        return {'subject_id':subject.entity_id,'observed_at':None if row is None else row['at'],
            'status':'observed' if current and row['senses'] is not None else 'unknown','senses':deepcopy(row['senses']) if current else None}
    return {'subject_id':subject.entity_id,'intentions':None if row is None else row['intentions'],
        'emotions':None if row is None else row['emotions'],'motivations':None if row is None else row['motivations'],
        'moves':deepcopy(subject.moves),'abilities':deepcopy(subject.abilities),
        'capabilities':list(G.effective_capabilities(subject)),
        'past_hour':None if row is None or row['memories'] is None else deepcopy([v for v in row['memories'] if engine.elapsed_seconds-3600<=v['at']<=engine.elapsed_seconds])}


DIVINATION_FACTS='divination_observation_facts'


def divination_target(engine,observer,mode,target=None):
    W.require_actors(engine,observer)
    if mode=='augury':
        if target is not None and target is not observer:raise ValueError('Augury targets Self')
        return {'kind':'self','target_id':observer.entity_id}
    if mode!='scrying':raise ValueError('actual Augury or Scrying required')
    if target is None:
        loc=W.effective_location(engine,observer)
        if loc['kind']=='unknown':raise ValueError('actual current Scrying location required')
        return {'kind':'location','location':loc}
    uid=_actual(engine,observer,target)
    if type(target)is not dict or target.get('kind')!='item_instance':raise ValueError('Scrying targets a touched actual item or current location')
    W.require_usable_object(target)
    import held_equipment as HELD
    held=any(x.get('instance_id')==uid for x in HELD.entries(observer))
    if not held:
        declaration_value=native(__import__('oracle').DIVINATION,[],mode='touch')
        declaration_value['path']='touch'
        _,_,blocked=route(engine,observer,target,declaration_value)
        if blocked is not None:raise ValueError('actual observed Scrying contact required')
    return {'kind':'item','target_id':uid}


def record_divination_fact(engine,observer,mode,events,*,reason,target=None,clarity='clear',memory='remembered'):
    import oracle as O
    O.require(engine,observer,O.DIVINATION);Q._text(reason)
    binding=divination_target(engine,observer,mode,target)
    if clarity not in ('clear','unclear','jumbled') or memory not in ('remembered','partial','forgotten'):raise ValueError('explicit GM vision clarity and recall required')
    if type(events)is not list:raise ValueError('GM vision events must be a list; empty means unknown')
    for event in events:
        Q._fields(event,('at','text'));C.integer(event['at'],'vision event time',0);Q._text(event['text'])
        if mode=='scrying' and event['at']>engine.elapsed_seconds:raise ValueError('Scrying cannot reveal future events')
    def apply(e,a):
        row={'source':'gm/divination','observer_id':a.entity_id,'mode':mode,'binding':deepcopy(binding),'events':deepcopy(events),
            'clarity':clarity,'memory':memory,'at':e.elapsed_seconds,'reason':reason}
        row['sha256']=TX.request_fingerprint(row)
        a.spec.setdefault(DIVINATION_FACTS,[]).append(row);e.gm._rec('Divination vision',None,row,reason,a)
        return deepcopy(row)
    return G.transition(engine,observer,apply,include_rulings=True)


def validate_divination_facts(engine,actor):
    rows=actor.spec.get(DIVINATION_FACTS,[])
    if type(rows)is not list:raise ValueError('observed Divination fact list required')
    for row in rows:
        if row.get('sha256')!=TX.request_fingerprint({k:v for k,v in row.items() if k!='sha256'}) or row.get('source')!='gm/divination' or row.get('observer_id')!=actor.entity_id:raise ValueError('GM Divination fact provenance changed')
        C.integer(row['at'],'Divination observation time',0,engine.elapsed_seconds)
        if row['mode'] not in ('augury','scrying') or row['clarity'] not in ('clear','unclear','jumbled') or row['memory'] not in ('remembered','partial','forgotten'):raise ValueError('GM Divination interpretation changed')
        for event in row['events']:C.integer(event['at'],'observed event time',0);Q._text(event['text'])


def divination_information(engine,observer,mode,binding):
    validate_divination_facts(engine,observer)
    row=next((r for r in reversed(observer.spec.get(DIVINATION_FACTS,[])) if r['mode']==mode and r['binding']==binding),None)
    events=[] if row is None or row['memory']=='forgotten' else deepcopy(row['events'])
    if mode=='scrying':events=[v for v in events if engine.elapsed_seconds-86400<=v['at']<=engine.elapsed_seconds]
    return {'source':__import__('oracle').DIVINATION,'mode':mode,'binding':deepcopy(binding),'observed_at':None if row is None else row['at'],
        'status':'unknown' if not events else 'observed','events':events,'clarity':None if row is None else row['clarity'],'memory':None if row is None else row['memory']}


def pickup_item_choice(engine,actor,category,chosen,reason):
    """The printed table chooses a category; the GM supplies the actual object."""
    Q._fields(chosen,('item_id','instance_id','category','reason'))
    if chosen['category']!=category:raise ValueError('GM specific item must belong to the rolled category')
    Q._text(chosen['reason']);Q._text(chosen['instance_id'])
    effects,header=engine.r.item_effects(chosen['item_id'])
    if effects is None or header.get('id')!=chosen['item_id']:raise ValueError('GM Pickup choice needs an exact real item rule')
    if chosen['instance_id'] in W.entity_index(engine):raise ValueError('Pickup cannot duplicate an existing physical identity')
    W.register_object(engine,chosen['instance_id'],location=W.effective_location(engine,actor),reason=reason+'; '+chosen['reason'],
        kind='item_instance',item_rule_id=chosen['item_id'],owner_id=actor.entity_id,source=__import__('oracle').PICKUP)
    return deepcopy(engine._physical_objects[chosen['instance_id']])
