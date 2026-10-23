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
    permitted={'entity':ENTITY_FIELDS,'aura':('presence',*A.FIELDS),'surface':('presence','surface_thought')}
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
    for actor in index.values():
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
    chosen=list(value['information']) if information is None else information;_names(chosen)
    if not set(chosen)<=set(value['information']):raise ValueError('information exceeds this actual sensing declaration')
    current={S.key(name) for name in G.effective_capabilities(observer)}
    if value['capabilities'] and not current.intersection(S.key(name) for name in value['capabilities']):raise ValueError('current declared sensing capability required')
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
        result=C.against_dc(e.skill_roll(c,check['skill'],skill_target=other,**options),check['dc'])
        sensed=_values(e,c,other,value,chosen) if result.passed else _result(value,'not_observable','check_failed')
        import optional_physical_equipment as OPTIONAL_EQUIPMENT
        sensed=OPTIONAL_EQUIPMENT.reveal_observation(e,c,other,sensed)
        sensed['check']={'passed':result.passed,'total':result.total,'dc':check['dc']}
        return sensed
    return G.transition(engine,observer,apply,participants=(target,))
