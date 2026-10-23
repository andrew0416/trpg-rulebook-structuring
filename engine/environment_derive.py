"""Live region facts and narrowly scoped environmental numeric contributions."""
from copy import deepcopy
import common_checks as C,crafting_recipes as Q,world_entities as W,state_grants as G
import composition_derive as D,resolution_transaction as TX,body_state as BODY

FIELD='_environment_derive'
ENVIRONS=('초원','숲','늪지','바다','설원','산','동굴','도시','사막')
FAMILIES={'gravity':{'gravity','relative_gravity','zero_gravity'},'pressure':{'pressure','air_available','medium'},'weather':{'weather'},'terrain':{'rough','slow'}}
TARGETS={'skill','evasion','movement','power'}
OPS={'eq','ne','lt','le','gt','ge'}


def _state(e):return getattr(e,FIELD,{'version':1,'regions':{},'actors':{}})
def _sign(row):return dict(row,sha256=TX.request_fingerprint(row))
def _verify(row):
    if type(row) is not dict or row.get('sha256')!=TX.request_fingerprint({k:v for k,v in row.items() if k!='sha256'}):raise ValueError('environment observation or binding changed')


def _number(value,positive=False):
    from root_resolution import _number
    out=_number(value)
    if out<0 or (positive and out==0):raise ValueError('nonnegative environment quantity required')
    return out


def facts(value):
    if type(value) is not dict:raise ValueError('environment fact mapping required')
    Q._fields({k:v for k,v in value.items() if k!='environ'},('gravity','pressure','air_available','medium'))
    for key in ('gravity','pressure'):
        if value[key] is not None:_number(value[key])
    if value['air_available'] is not None and type(value['air_available']) is not bool:raise ValueError('observed air availability required')
    if value['medium'] is not None and value['medium'] not in ('air','water','airless'):raise ValueError('observed breathing medium required')
    if value['medium']=='airless' and value['air_available'] is True:raise ValueError('airless region cannot supply breathing air')
    if value.get('environ') is not None and value['environ'] not in ENVIRONS:raise ValueError('observed Environ table environment required')
    return deepcopy(value)


def declaration(value):
    Q._fields(value,('id','source','home_gravity','rules'))
    Q._text(value['id']);Q._text(value['source']);_number(value['home_gravity'],True)
    if type(value['rules']) is not list:raise ValueError('environment rule list required')
    ids=set()
    for row in value['rules']:
        Q._fields(row,('id','family','target','selector','when','law','value','priority','exemption'))
        Q._text(row['id']);Q._text(row['selector'])
        if row['id'] in ids:raise ValueError('duplicate environmental contribution')
        ids.add(row['id'])
        if row['family'] not in FAMILIES or row['target'] not in TARGETS or row['law'] not in D.LAWS:raise ValueError('known environmental family, target and law required')
        C.integer(row['priority'],'environment contribution priority')
        if type(row['when']) is not list or not row['when']:raise ValueError('explicit environmental conditions required')
        for item in row['when']:
            Q._fields(item,('fact','op','value'))
            if item['fact'] not in FAMILIES[row['family']] or item['op'] not in OPS:raise ValueError('environment condition differs from declared family')
            if item['value'] is None:raise ValueError('known environmental comparison required')
            if item['fact'] in ('gravity','relative_gravity','pressure'):_number(item['value'])
            elif item['op'] not in ('eq','ne'):raise ValueError('categorical environment conditions require equality')
            elif item['fact'] in ('air_available','zero_gravity','rough','slow') and type(item['value']) is not bool:raise ValueError('boolean environmental condition required')
        from root_resolution import _number as numeric
        amount=numeric(row['value'])
        if row['exemption'] not in ('none','gravity_tolerance'):raise ValueError('explicit environmental exemption required')
        if row['exemption']=='gravity_tolerance' and not (row['family']=='gravity' and row['target'] in ('skill','evasion') and row['law']=='add' and amount<0):raise ValueError('gravity tolerance exempts only declared skill/evasion penalties')
    return deepcopy(value)


def _cells(e,cells):
    if cells is None:return None
    if e.grid is None or type(cells) is not list or not cells:raise ValueError('actual mapped region cells required')
    import terrain_actions as T
    points=[T.point(cell) for cell in cells]
    if len(set(points))!=len(points) or any(not e.grid.inside(cell) for cell in points):raise ValueError('distinct in-map region cells required')
    return [list(p) for p in sorted(points)]


def observe_region(e,region_id,value,*,cells=None,source,reason):
    Q._text(region_id);Q._text(reason);Q._selected(e,source)
    row=_sign({'id':region_id,'source':source,'facts':facts(value),'cells':_cells(e,cells),'reason':reason,'seconds':e.elapsed_seconds})
    if region_id in _state(e)['regions']:raise ValueError('existing region changes require environment change entry point')
    state=deepcopy(_state(e));state['regions'][region_id]=row
    setattr(e,FIELD,state)
    return deepcopy(row)


def bind(e,c,value,*,region_id=None,reason):
    W.require_actors(e,c);Q._text(reason);value=declaration(value);Q._selected(e,value['source'])
    if region_id is not None:
        if region_id not in _state(e)['regions'] or e.grid is not None:raise ValueError('explicit region binding is only for actual unmapped actors')
    row=_sign({'actor_id':c.entity_id,'declaration':value,'region_id':region_id,'reason':reason,'seconds':e.elapsed_seconds})
    if c.entity_id in _state(e)['actors']:raise ValueError('environment actor baseline is already observed')
    state=deepcopy(_state(e));state['actors'][c.entity_id]=row;setattr(e,FIELD,state)
    return deepcopy(row)


def bound(e,c):return c.entity_id in _state(e)['actors']


def region(e,c):
    """Current spatial region, independent of a numeric/home-gravity policy."""
    W.require_actors(e,c);state=_state(e)
    if e.grid is not None:
        body=set(BODY.cells(c))
        candidates=[row for row in state['regions'].values() if row['cells'] is None or body<=set(map(tuple,row['cells']))]
    else:
        binding=state['actors'].get(c.entity_id)
        if binding is not None:
            _verify(binding);Q._selected(e,binding['declaration']['source'])
            uid=binding['region_id']
        else:
            import mapless_space as MAPLESS
            actual,frame=MAPLESS._context(e,c);mapping=actual.get('environment')
            if mapping is None:raise ValueError('current mapless place needs an observed environment region')
            MAPLESS._verify(mapping);MAPLESS._environment_regions(e,actual['places'],mapping['places'])
            uid=mapping['places'].get(frame['positions'][c.entity_id]['place_id'])
        candidates=[state['regions'][uid]] if uid in state['regions'] else []
    if len(candidates)!=1:raise ValueError('one observed region covering the actual full body required')
    row=candidates[0];_verify(row);Q._selected(e,row['source'])
    return deepcopy(row)


def context(e,c):
    W.require_actors(e,c);state=_state(e);binding=state['actors'].get(c.entity_id)
    if binding is None:raise ValueError('actual environment actor baseline required')
    _verify(binding);value=declaration(binding['declaration']);Q._selected(e,value['source'])
    body=set(BODY.cells(c)) if e.grid is not None else None
    current=region(e,c)
    import environment_change as EC
    actual=EC.effective(e,current)
    from root_resolution import plain,_numeric_value
    actual['relative_gravity']=None if actual['gravity'] is None else plain(_numeric_value(_number(actual['gravity'])/_number(value['home_gravity'],True)))
    actual['zero_gravity']=None if actual['gravity'] is None else _number(actual['gravity'])==0
    actual['weather']=__import__('effects').effective_weather(e,c) or 'clear'
    actual['rough']=None if body is None else bool(body.intersection(e.grid.rough))
    actual['slow']=None if body is None else bool(body.intersection(e.grid.slow))
    actual.update(region_id=current['id'],actor_id=c.entity_id,home_gravity=value['home_gravity'])
    return actual


def _matches(actual,conditions):
    from root_resolution import _number as numeric
    results=[]
    for item in conditions:
        left=actual[item['fact']]
        if left is None:raise ValueError('required environment fact is unknown: '+item['fact'])
        right=item['value']
        if item['fact'] in ('gravity','relative_gravity','pressure'):left,right=numeric(left),numeric(right)
        op=item['op']
        results.append({'eq':lambda:left==right,'ne':lambda:left!=right,'lt':lambda:left<right,'le':lambda:left<=right,'gt':lambda:left>right,'ge':lambda:left>=right}[op]())
    return all(results)


def derive(e,c,target,selector,base):
    if target not in TARGETS:raise ValueError('supported environment numeric target required')
    if not bound(e,c):return D.derive(base,[],[])
    actual=context(e,c);value=_state(e)['actors'][c.entity_id]['declaration']
    names={str(x).removeprefix('capability/') for x in G.effective_capabilities(c)}
    tolerant=bool(names.intersection({'중력내성','중력 내성','GravityTolerance','Gravity Tolerance'}))
    rows=[];steps=[];exempt=[]
    for rule in value['rules']:
        if rule['target']!=target or rule['selector'] not in ('*',selector):continue
        active=_matches(actual,rule['when'])
        if active and tolerant and rule['exemption']=='gravity_tolerance':exempt.append(rule['id']);active=False
        rows.append({'id':rule['id'],'source':value['source'],'value':rule['value'],'priority':rule['priority'],'active':active})
        steps.append({'law':rule['law'],'contributors':[rule['id']]})
    return dict(D.derive(base,rows,steps),context=actual,exempt=exempt)


def movement(e,c,values):
    if not bound(e,c):return values
    return {key:max(0,derive(e,c,'movement',key,value)['value']) if type(value) is int else value for key,value in values.items()}


def skill(e,c,skill):
    if not bound(e,c):return ()
    # Skill modifiers are a numeric channel; dice count and native rank stay native.
    result=derive(e,c,'skill',skill,0)
    return ((_state(e)['actors'][c.entity_id]['declaration']['source'],result['value'],result['context']['region_id']),)


def respiration(e,c,fallback):
    if not bound(e,c):return fallback
    actual=context(e,c)
    if actual['air_available'] is None or actual['medium'] is None:raise ValueError('actual atmospheric breathing facts are unknown')
    if (fallback['air_available'],fallback['medium'])!=(actual['air_available'],actual['medium']):raise ValueError('breathing observation differs from actual current region')
    return dict(fallback,air_available=actual['air_available'],medium=actual['medium'])


def validate_world(e,index):
    if not hasattr(e,FIELD):return
    state=_state(e);Q._fields(state,('version','regions','actors'))
    if state['version']!=1 or type(state['regions']) is not dict or type(state['actors']) is not dict:raise ValueError('environment world schema required')
    for uid,row in state['regions'].items():
        _verify(row);Q._fields({k:v for k,v in row.items() if k!='sha256'},('id','source','facts','cells','reason','seconds'))
        if row['id']!=uid:raise ValueError('region identity mismatch')
        facts(row['facts']);_cells(e,row['cells']);Q._text(row['reason']);Q._selected(e,row['source']);C.integer(row['seconds'],'environment observation time',0)
        if row['seconds']>e.elapsed_seconds:raise ValueError('environment observation in future')
    for uid,row in state['actors'].items():
        _verify(row);Q._fields({k:v for k,v in row.items() if k!='sha256'},('actor_id','declaration','region_id','reason','seconds'))
        if uid!=row['actor_id'] or uid not in index:raise ValueError('actual environment actor required')
        declaration(row['declaration']);Q._selected(e,row['declaration']['source']);Q._text(row['reason']);C.integer(row['seconds'],'environment baseline time',0)
        if row['seconds']>e.elapsed_seconds or (row['region_id'] is not None and row['region_id'] not in state['regions']):raise ValueError('actual region and baseline time required')


def evasion(e,c,move,mechanics):
    if not bound(e,c) or c.fainted:return 0
    kind=move['class']
    for row in mechanics.get('effects_exec',[]):
        if row.get('type')=='damage_formula_override':kind={'def':'물리','spd':'특수'}.get(row.get('defense_stat'),kind)
    base=c.evasion(kind)
    return derive(e,c,'evasion',kind,base)['value']-base

