"""Capability body modes: sourced size, evasion, footprint and action lifetime."""
from copy import deepcopy,copy
from math import isfinite
import state_grants as G
KEY='body_mode'
DEFINITIONS={'inflate':{'capability':'팽창성','source':'capability/팽창성','minimum':1,'maximum':1.25,'evasion':-1,'return_action':'shift'},
             'shrink':{'capability':'수축성','source':'capability/수축성','minimum':0.25,'maximum':1,'evasion':4,'return_action':'standard'},
             'shapeshift':{'capability':'형상변환자','source':'capability/형상변환자','minimum':1,'maximum':1,'evasion':0,'return_action':'standard'},
             'amorphous':{'capability':'부정형','source':'capability/부정형','evasion':0,'return_action':None},
             'phasing':{'capability':'페이징','aliases':('페이징','Phasing','통과'),'source':'capability/페이징','minimum':1,'maximum':1,'evasion':0,'return_action':'shift'},
             'shadow':{'capability':'그림자숨기','aliases':('그림자숨기','Shadow Meld'),'source':'capability/그림자숨기','minimum':1,'maximum':1,'evasion':1,'return_action':'shift'}}
SPIRIT_MODES={'phasing','shadow'}
SPIRIT_SOURCE={'file':'input/ch10-index-reference.md','sha256':'c3a1d783b4f649f0f6e25a9443a90ca8079a6e036c42c6f8797e100127157abe'}


def _spirit_source(actor,mode):
 if mode not in SPIRIT_MODES:return
 from source_context import verified_source
 verified_source(actor.r,SPIRIT_SOURCE,label=mode+' body mode')
 if actor.kind!='pokemon':raise ValueError('Phasing and Shadow Meld require an actual Pokemon')
 if mode=='shadow' and actor.spec.get('species')!='pokemon/팬텀':raise ValueError('Shadow Meld requires the source-listed actual Gengar species')


def validate(actor):
 row=actor.spec.get(KEY)
 if row is None:return None
 if not isinstance(row,dict) or row.get('mode') not in DEFINITIONS:raise ValueError('reviewed body mode required')
 definition=DEFINITIONS[row['mode']]
 if row.get('source')!=definition['source'] or actor.r._selected_rule(row['source'])!=row['source']:raise ValueError('selected body mode source mismatch')
 _spirit_source(actor,row['mode'])
 ratio=row.get('size_ratio')
 if row['mode']=='amorphous':
  if ratio is not None:raise ValueError('Amorphous has no source-defined linear size ratio')
 elif type(ratio) not in (int,float) or not isfinite(ratio) or not definition['minimum']<=ratio<=definition['maximum'] or (ratio==1 and row['mode'] not in ('shapeshift',*SPIRIT_MODES)):raise ValueError('body mode size ratio outside source bounds')
 if not isinstance(row.get('reason'),str) or not row['reason'].strip():raise ValueError('observed body-mode geometry reason required')
 fields={'mode','source','size_ratio','reason','footprint'}
 if row['mode'] in SPIRIT_MODES:
  fields.add('actor_id')
  if row.get('actor_id')!=actor.entity_id:raise ValueError('spirit body mode belongs to another actual Pokemon')
 if row['mode']=='phasing':
  fields.update(('round_loss','last_loss_round'))
  loss=row.get('round_loss')
  if type(loss)is not dict or set(loss)!={'amount','reason','source'} or loss['source']!='gm/observation':raise ValueError('Phasing requires an explicit GM observation of the unspecified small HP loss')
  import common_checks as C
  C.integer(loss['amount'],'observed small Phasing HP loss',1)
  if not isinstance(loss['reason'],str) or not loss['reason'].strip():raise ValueError('reason for the observed small Phasing HP loss required')
  if row['last_loss_round'] is not None:C.integer(row['last_loss_round'],'last actual Phasing round',0)
 if row['mode']=='shadow':
  fields.update(('host','motion'))
  host=row.get('host')
  if host is not None:
   if type(host)is not dict or set(host)!={'actor_id','offset','reason'} or not isinstance(host['actor_id'],str) or not host['actor_id'] or host['actor_id']==actor.entity_id:raise ValueError('distinct actual shadow host identity required')
   if not isinstance(host['offset'],(list,tuple)) or len(host['offset'])!=2 or any(type(v)is not int for v in host['offset']):raise ValueError('observed host shadow offset required')
   if not isinstance(host['reason'],str) or not host['reason'].strip():raise ValueError('actual host shadow observation reason required')
  motion=row.get('motion')
  if motion is not None:
   if type(motion)is not dict or set(motion)!={'id','declaration','plan','progress'} or not isinstance(motion['id'],str) or not motion['id']:raise ValueError('actual paid shadow surface motion required')
   import resolution_transaction as TX
   if motion['declaration'].get('sha256')!=TX.json_fingerprint({k:v for k,v in motion['declaration'].items() if k!='sha256'}):raise ValueError('observed shadow surface declaration changed')
   if motion['declaration'].get('plan_sha256')!=TX.json_fingerprint(motion['plan']):raise ValueError('paid shadow surface plan differs from its observed declaration')
   if [{k:v for k,v in node.items() if k!='diagonals'} for node in motion['plan']['path']]!=motion['declaration']['path']:raise ValueError('paid shadow surface route differs from its observed declaration')
 if row['mode']=='amorphous':
  fields.update(('actor_id','form','height_m','cross_section'))
  if row.get('actor_id')!=actor.entity_id:raise ValueError('observed Amorphous form belongs to another actual body')
  if not isinstance(row.get('form'),str) or not row['form'].strip():raise ValueError('observed Amorphous form required')
  height=row.get('height_m');section=row.get('cross_section')
  if height is not None and (type(height) not in (int,float) or not isfinite(height) or height<=0):raise ValueError('observed body height must be positive')
  if section is not None:
   if type(section)is not dict or set(section)!={'axis','width_m'} or section['axis'] not in ('x','y'):raise ValueError('observed body cross-section axis and width required')
   width=section['width_m']
   if height is None or type(width) not in (int,float) or not isfinite(width) or width<=0:raise ValueError('observed positive body cross-section measurements required')
 if row['mode']=='shapeshift':
  if 'volume_ratio' in row:raise ValueError('legacy volume shapeshift is not official mass state; reapply with mass_ratio')
  fields.update(('mass_ratio','mass_weight_class','appearance','height_m'))
  mass=row.get('mass_ratio')
  if type(mass) not in (int,float) or not isfinite(mass) or not 0.5<=mass<=1.5:raise ValueError('shapeshift mass must remain 50 to 150 percent of original')
  import body_state as BODY
  BODY.shapeshift_mass(actor,row)
  BODY.shapeshift_weight_class(actor,row)
  appearance=row.get('appearance')
  if not isinstance(appearance,dict) or set(appearance)!={'kind','description'} or appearance['kind'] not in ('object','moving_object','complex_machine','pokemon') or not isinstance(appearance['description'],str) or not appearance['description'].strip():raise ValueError('observed appearance kind and description required')
  height=row.get('height_m')
  if height is not None and (type(height) not in (int,float) or not isfinite(height) or height<=0):raise ValueError('observed shapeshift height must be positive')
 if set(row)!=fields:raise ValueError('unreviewed body mode payload')
 import body_state as BODY
 probe=copy(actor);probe.spec=dict(actor.spec);probe.spec.pop(KEY,None);probe.spec['footprint']=row['footprint'];BODY.validate(probe)
 return row


def evasion(actor):
 row=validate(actor);return DEFINITIONS[row['mode']]['evasion'] if row else 0


def permits(actor,kind,*,returning=False):
 row=validate(actor)
 if not row or row['mode'] not in ('shrink',*SPIRIT_MODES):return True
 if row['mode']=='shadow' and row['motion'] is not None and row['motion']['progress'].get('phase') not in ('complete','stopped'):return False
 budget=getattr(actor,'budget',None)
 uses_standard=kind in ('standard','full') or (kind in ('swift','shift') and budget is not None and budget.get(kind,0)<=0 and budget.get('standard',0)>0)
 return not uses_standard or (row['mode']=='shrink' and returning is True and kind=='standard')


def change(engine,actor,mode,*,size_ratio=None,offsets=None,mass_ratio=None,mass_weight_class=None,volume_ratio=None,appearance=None,height_m=None,form=None,cross_section=None,round_loss=None,loss_reason=None,shadow_host=None,shadow_offset=(0,0),reason):
 import world_entities as W
 if W.actor_index(engine).get(actor.entity_id)is not actor:raise ValueError('actual registered body required')
 if volume_ratio is not None:raise ValueError('legacy volume shapeshift is not official mass state; use mass_ratio')
 if mode!='shapeshift' and any(x is not None for x in (mass_ratio,mass_weight_class,appearance)):raise ValueError('appearance inputs require shapeshift mode')
 if mode not in ('shapeshift','amorphous') and height_m is not None:raise ValueError('observed height requires a supported body form')
 if mode!='amorphous' and (form is not None or cross_section is not None):raise ValueError('Amorphous observation inputs require Amorphous mode')
 if mode!='phasing' and (round_loss is not None or loss_reason is not None):raise ValueError('small HP loss observation belongs only to Phasing')
 if mode!='shadow' and shadow_host is not None:raise ValueError('actual shadow host belongs only to Shadow Meld')
 if shadow_host is not None and W.actor_index(engine).get(shadow_host.entity_id)is not shadow_host:raise ValueError('actual registered shadow host required')
 if not isinstance(reason,str) or not reason.strip():raise ValueError('body-mode reason required')
 def apply(e,c):
  import turn as TURN,body_state as BODY
  old=validate(c)
  if mode=='normal':
   if old is None:raise ValueError('no active body mode to end')
   if size_ratio is not None or offsets is not None:raise ValueError('return uses unchanged original body')
   candidate=copy(c);candidate.spec=dict(c.spec);candidate.spec.pop(KEY,None)
   cost=DEFINITIONS[old['mode']]['return_action']
  else:
   if mode not in DEFINITIONS:raise ValueError('reviewed body mode required')
   if old and not (old['mode']==mode and mode in ('shapeshift','amorphous')):raise ValueError('return to original body before applying another body mode')
   definition=DEFINITIONS[mode]
   if mode=='amorphous' and c.kind!='pokemon':raise ValueError('native Amorphous form requires an actual Pokemon')
   names=definition.get('aliases',(definition['capability'],))
   import skill_modifiers as SKILLS
   if not {SKILLS.key(x) for x in names}.intersection(SKILLS.key(str(x).removeprefix('capability/')) for x in G.effective_capabilities(c,only=names)):raise ValueError('actual body capability required')
   if mode in SPIRIT_MODES:
    _spirit_source(c,mode)
    if size_ratio is not None:raise ValueError('Phasing and Shadow Meld do not define a size ratio')
    size_ratio_value=1
    # Becoming intangible does not resize the actual body's existing footprint.
    if offsets is None:offsets_value=BODY.offsets(c)
    else:offsets_value=offsets
    if mode=='phasing' and tuple(tuple(q) for q in offsets_value or ())!=BODY.offsets(c):raise ValueError('Phasing preserves the actual body footprint')
   else:size_ratio_value=size_ratio;offsets_value=offsets
   if offsets_value is None:raise ValueError('observed occupied cells for changed size required')
   candidate=copy(c);candidate.spec=dict(c.spec)
   candidate.spec[KEY]={'mode':mode,'source':definition['source'],'size_ratio':size_ratio_value,'reason':reason,'footprint':{'kind':'observed_cells','offsets':deepcopy(offsets_value),'reason':reason}}
   if mode in SPIRIT_MODES:candidate.spec[KEY]['actor_id']=c.entity_id
   if mode=='phasing':candidate.spec[KEY].update(round_loss={'amount':round_loss,'source':'gm/observation','reason':loss_reason},last_loss_round=None)
   if mode=='shadow':
    host=None
    if shadow_host is not None:
     actual=W.actor_index(e)[shadow_host.entity_id]
     if actual is c or actual.kind not in ('pokemon','trainer') or actual.dead or actual.captured or not actual.on_field:raise ValueError('actual other living creature shadow required')
     if c.pos!=tuple(actual.pos[i]+shadow_offset[i] for i in (0,1)) or c.spec.get('_movement_altitude',0)!=actual.spec.get('_movement_altitude',0):raise ValueError('enter the observed host shadow at the current actual position')
     host={'actor_id':actual.entity_id,'offset':list(shadow_offset),'reason':reason}
    candidate.spec[KEY].update(host=host,motion=None)
   if mode=='shapeshift':
    if size_ratio is not None:raise ValueError('shapeshift mass does not imply linear size ratio')
    candidate.spec[KEY].update(size_ratio=1,mass_ratio=mass_ratio,mass_weight_class=mass_weight_class,appearance=deepcopy(appearance),height_m=height_m)
   if mode=='amorphous':
    # Core p303 specifies no action cost or duration. This records an actual
    # observed form, without issuing a free-action or movement permission.
    candidate.spec[KEY].update(actor_id=c.entity_id,form=form,height_m=height_m,cross_section=deepcopy(cross_section))
   validate(candidate);cost=None if mode=='amorphous' else 'standard'
  if e.grid is not None:
   occupied=BODY.cells(candidate,require_complete=True)
   if any(not e.grid.inside(cell) or cell in e.grid.blocking for cell in occupied) or (not flat(candidate) and occupied.intersection(e.occupied(c))):raise ValueError('changed body does not fit actual map')
  if cost is not None and not TURN.spend(e,c,cost,'body mode '+mode,_body_mode_return=(mode=='normal')):raise ValueError('body mode action unavailable')
  if mode=='normal':c.spec.pop(KEY,None)
  else:c.spec[KEY]=deepcopy(candidate.spec[KEY])
  e.gm._rec('신체 크기 상태',deepcopy(old),deepcopy(c.spec.get(KEY)),reason,c)
  validate_world(e,W.actor_index(e))
  return BODY.projection(c)
 return G.transition(engine,actor,apply)


def movement_blocked(engine,actor,origin,target,*,altitude,underground):
 """A measured aperture only relaxes its own cardinal movement surface."""
 grid=engine.grid
 if not grid.blocked(origin,target):return False
 if altitude!=0 or underground or abs(target[0]-origin[0])+abs(target[1]-origin[1])!=1:return True
 edge=tuple(sorted((origin,target)))
 if target in grid.blocking or edge not in grid.walls:return True
 row=validate(actor)
 if not row or row['mode']!='amorphous' or row['cross_section'] is None:return True
 if '부정형' not in G.effective_capabilities(actor,only=('부정형',)):return True
 axis='x' if origin[0]!=target[0] else 'y'
 if row['cross_section']['axis']!=axis:return True
 import body_state as BODY
 return not BODY.fits_observed_passage(engine,edge,height_m=row['height_m'],width_m=row['cross_section']['width_m'])


def blocks_line(engine,origin,target,*,ignored=()):
 if engine.grid is None:return False
 import body_state as BODY
 path=set(engine.grid.line_cells(origin,target))
 for c in getattr(engine,'everyone',[]) or []:
  if any(c is x for x in ignored) or not c.on_field or c.captured:continue
  row=validate(c)
  if row and row['mode']=='inflate' and path.intersection(BODY.cells(c,require_complete=True)):return True
 return False


def target_visible(engine,actor,target):
 if not targetable(target,attack=False):return False
 if engine.grid is None:return True
 if not any((validate(c) or {}).get('mode')=='inflate' and c.on_field and not c.captured for c in getattr(engine,'everyone',[]) or []):return True
 import body_state as BODY
 return any(not blocks_line(engine,a,b,ignored=(actor,target)) for a in BODY.cells(actor,require_complete=True) for b in BODY.cells(target,require_complete=True))


def targetable(actor,*,attack=True):
 import marsupial_state as MARSUPIAL
 return not (attack and MARSUPIAL.in_pouch(actor)) and (validate(actor) or {}).get('mode')!='phasing'


def require_targetable(actor,*,attack=True):
 import marsupial_state as MARSUPIAL
 if attack and MARSUPIAL.in_pouch(actor):raise ValueError('native Marsupial baby is protected in its actual mother pouch')
 if not targetable(actor,attack=attack):raise ValueError('Phasing body cannot be a Move or attack target')


def flat(actor):
 return (validate(actor) or {}).get('mode')=='shadow'


def stealth(actor,skill):
 import skill_modifiers as S
 return 4 if flat(actor) and S.skill_id(actor.r.skill_policy,skill)==S.skill_id(actor.r.skill_policy,'은신') else 0


def movement_permission(actor):
 row=validate(actor)
 return not (row and row['mode']=='shadow' and row['host'] is not None)


def finish_round(engine):
 import combat_state_lifecycle as COMBAT
 for actor in COMBAT.members(engine):
  row=validate(actor)
  if not row or row['mode']!='phasing' or row['last_loss_round']==engine.round_no:continue
  engine.lose_hp(actor,row['round_loss']['amount'],row['source'])
  row['last_loss_round']=engine.round_no


def sync_shadows(engine):
 """Follow an actual host's committed location; no mount, load or action grant."""
 import world_entities as W
 index=W.actor_index(engine);done=set();visiting=set()
 def sync(actor):
  if actor.entity_id in done:return
  if actor.entity_id in visiting:raise ValueError('cyclic shadow host relation')
  visiting.add(actor.entity_id);row=validate(actor)
  if row and row['mode']=='shadow' and row['host'] is not None:
   host=index.get(row['host']['actor_id'])
   if host is None:raise ValueError('actual shadow host is missing')
   sync(host)
   if host.captured or not host.on_field:
    row['host']=None
   else:
    location=W.location_of(host)
    if location['kind']=='grid':location=dict(location,cell=[location['cell'][i]+row['host']['offset'][i] for i in (0,1)])
    actor.location=deepcopy(location)
    actor.spec['_movement_altitude']=host.spec.get('_movement_altitude',0)
    actor.airborne=False
  visiting.remove(actor.entity_id);done.add(actor.entity_id)
 for actor in index.values():sync(actor)


def validate_world(engine,index):
 import world_entities as W
 for obj in getattr(engine,'_physical_objects',{}).values():
  if '_shadow_surface' in obj:_surface_observation(obj)
 for actor in index.values():
  row=validate(actor)
  if not row or row['mode']!='shadow':continue
  host=row['host'];seen={actor.entity_id}
  while host is not None:
   if host['actor_id'] in seen:raise ValueError('cyclic shadow host relation')
   seen.add(host['actor_id']);other=index.get(host['actor_id'])
   if other is None or other.kind not in ('pokemon','trainer'):raise ValueError('actual shadow host is missing')
   next_row=validate(other);host=next_row['host'] if next_row and next_row['mode']=='shadow' else None
  host=row['host']
  if host is not None:
   other=index[host['actor_id']];expected=W.location_of(other)
   if expected['kind']=='grid':expected=dict(expected,cell=tuple(expected['cell'][i]+host['offset'][i] for i in (0,1)))
   if W.location_of(actor)!=expected or actor.spec.get('_movement_altitude',0)!=other.spec.get('_movement_altitude',0):raise ValueError('shadow body no longer follows its actual host')
  motion=row['motion']
  if motion is not None:
   import movement_actions as MOVE
   path=[{k:v for k,v in node.items() if k!='diagonals'} for node in motion['plan']['path'][1:]]
   if motion['progress'].get('path')!=path:raise ValueError('paid shadow surface path changed')
   if motion['progress'].get('phase') not in ('complete','stopped'):
    import common_checks as C
    progress=motion['progress'];C.integer(progress.get('next'),'paid shadow surface prefix',0,len(path));C.integer(progress.get('distance'),'paid shadow surface distance',0,motion['plan']['distance'])
    if progress.get('phase') not in ('ready','entry_pending','reaction_pending'):raise ValueError('actual shadow surface continuation phase required')
    if tuple(progress.get('position',()))!=actor.pos or progress.get('altitude')!=actor.spec.get('_movement_altitude',0):raise ValueError('actual shadow surface prefix location changed')
 return True


def _surface_observation(obj):
 import resolution_transaction as TX,movement_actions as MOVE,world_entities as W
 from physical_limits import number
 row=obj.get('_shadow_surface')
 if type(row)is not dict or set(row)!={'object_id','source','reason','points','location','map_id','map_size','sha256'}:raise ValueError('actual observed shadow surface geometry required')
 if row['object_id']!=obj['id'] or row['source']!='gm/observation':raise ValueError('shadow surface belongs to another physical object')
 MOVE.reason(row['reason'])
 if row['sha256']!=TX.json_fingerprint({k:v for k,v in row.items() if k!='sha256'}):raise ValueError('observed shadow surface geometry changed')
 if type(row['points'])is not list or not row['points']:raise ValueError('actual surface contact points required')
 previous=None
 for node in row['points']:
  if type(node)is not dict or set(node)!={'position','altitude'}:raise ValueError('exact observed surface contact point required')
  point=MOVE._point(node['position']);height=number(node['altitude'],'observed surface contact altitude',minimum=0)
  if previous is not None and (max(abs(point[i]-previous[0][i]) for i in (0,1))>1 or abs(height-previous[1])>1):raise ValueError('observed physical surface contacts must be continuous')
  previous=point,height
 location=W.location_of(dict(location=row['location']))
 if location['kind']!='grid' or tuple(row['points'][0]['position'])!=tuple(location['cell']) or row['points'][0]['altitude']!=0:raise ValueError('observed surface must be anchored at its actual physical location')
 return row


def observe_shadow_surface(engine,object_id,points,*,reason):
 """Record actual connected contact geometry on a stationary physical object."""
 import world_entities as W,movement_actions as MOVE,resolution_transaction as TX
 MOVE.reason(reason)
 def apply(e,_):
  obj=getattr(e,'_physical_objects',{}).get(object_id)
  if obj is None or e.grid is None:raise ValueError('actual mapped physical surface required')
  W.require_usable_object(obj)
  if any(obj.get(k) for k in ('carrier_id','equipped_by','telekinetic_holder_id')):raise ValueError('actual stationary surface required')
  if not hasattr(e.grid,'_tunnel_map_id'):
   from uuid import uuid4
   e.grid._tunnel_map_id=str(uuid4())
  row=dict(object_id=object_id,source='gm/observation',reason=reason,points=deepcopy(points),location=W.location_of(obj),map_id=e.grid._tunnel_map_id,map_size=[e.grid.w,e.grid.h])
  row['sha256']=TX.json_fingerprint(row)
  old=deepcopy(obj.get('_shadow_surface'));obj['_shadow_surface']=row
  _surface_observation(obj)
  if any(not e.grid.inside(MOVE._point(node['position'])) for node in points):raise ValueError('surface contact outside actual map')
  e.gm._rec('actual shadow surface '+object_id,old,row,reason)
  return deepcopy(row)
 return G.transition(engine,None,apply,include_grid=True)


def shadow_contact(engine,actor,node):
 """Recheck the paid prefix's actual surface after native departure reactions."""
 import world_entities as W
 motion=validate(actor)['motion'];declaration=motion['declaration'];index=motion['progress']['next']+1
 if {k:v for k,v in motion['plan']['path'][index].items() if k!='diagonals'}!=node:raise ValueError('shadow surface step differs from its paid declaration')
 uid=declaration['surfaces'][index]
 if uid=='ground':return node['altitude']==0
 obj=getattr(engine,'_physical_objects',{}).get(uid)
 if obj is None or any(obj.get(k) for k in ('carrier_id','equipped_by','telekinetic_holder_id')):return False
 life=W.physical_lifecycle(obj)
 if life['consumed'] or life['destroyed']:return False
 row=_surface_observation(obj);fact=declaration['surface_objects'][index]
 return (engine.grid is not None and row['map_id']==getattr(engine.grid,'_tunnel_map_id',None)
         and row['map_size']==[engine.grid.w,engine.grid.h] and row['location']==W.location_of(obj)==fact['location']
         and row['sha256']==fact['contact_sha256']
         and any(tuple(p['position'])==tuple(node['position']) and p['altitude']==node['altitude'] for p in row['points']))


def shadow_move(engine,actor,path,*,movement_id,surfaces,reason):
 """Observed flat surface travel uses the existing paid physical path consumer."""
 import movement_actions as MOVE,world_entities as W,resolution_transaction as TX
 W.require_actors(engine,actor);MOVE.reason(movement_id);MOVE.reason(reason)
 row=validate(actor)
 if not row or row['mode']!='shadow':raise ValueError('actual active Shadow Meld required')
 def surface_facts(e):
  if type(surfaces)is not list or len(surfaces)!=len(path):raise ValueError('actual surface observation for every path point required')
  facts=[]
  for node,uid in zip(path,surfaces):
   if uid=='ground':
    if node['altitude']!=0:raise ValueError('ground contact cannot grant unsupported vertical travel')
    facts.append({'id':'ground'})
   else:
    obj=getattr(e,'_physical_objects',{}).get(uid)
    if obj is None or any(obj.get(k) for k in ('carrier_id','equipped_by','telekinetic_holder_id')):raise ValueError('actual stationary surface object required')
    W.require_usable_object(obj);contact=_surface_observation(obj)
    if e.grid is None or contact['map_id']!=getattr(e.grid,'_tunnel_map_id',None) or contact['map_size']!=[e.grid.w,e.grid.h] or contact['location']!=W.location_of(obj):raise ValueError('observed physical surface moved or belongs to another map')
    if not any(tuple(p['position'])==tuple(node['position']) and p['altitude']==node['altitude'] for p in contact['points']):raise ValueError('path point has no observed contact with the actual physical surface')
    facts.append({'id':uid,'location':W.location_of(obj),'contact_sha256':contact['sha256']})
  return facts
 declaration={'path':deepcopy(path),'surfaces':deepcopy(surfaces),'reason':reason,'surface_objects':surface_facts(engine)}
 def apply(e,c):
  import turn as TURN
  current=validate(c);motion=current['motion']
  if motion is not None and motion['id']==movement_id:
   if {k:v for k,v in motion['declaration'].items() if k not in ('sha256','plan_sha256')}!=declaration:raise ValueError('cannot replace an observed paid shadow surface path')
   if motion['progress'].get('phase') in ('complete','stopped'):
    progress=motion['progress']
    result={'distance':progress['distance'],'steps':progress['next'],'position':progress['position'],'mode':'shadow_surface','altitude':progress['altitude']}
    if progress['phase']=='stopped':result['stopped']=True
    return result
  else:
   if motion is not None and motion['progress'].get('phase') not in ('complete','stopped'):raise ValueError('finish the actually paid shadow surface path')
   plan=MOVE.observed_path(e,c,path)
   if plan['distance']>MOVE.distance_budget(e,c,'land'):raise ValueError('shadow surface path exceeds actual land movement')
   declaration['plan_sha256']=TX.json_fingerprint(plan)
   declaration['sha256']=TX.json_fingerprint(declaration)
   current['host']=None
   if not TURN.spend(e,c,'shift','Shadow Meld surface movement',movement=True):raise ValueError('shadow surface movement Shift unavailable')
   motion={'id':movement_id,'declaration':deepcopy(declaration),'plan':plan,'progress':{}}
   current['motion']=motion
  if surface_facts(e)!=motion['declaration']['surface_objects']:raise ValueError('observed shadow surface moved before traversal')
  paid_path=[{k:v for k,v in node.items() if k!='diagonals'} for node in motion['plan']['path'][1:]]
  result=MOVE.follow_paid_path(e,c,paid_path,mode='shadow_surface',maximum_distance=motion['plan']['distance'],progress=motion['progress'])
  if motion['progress']['phase']=='ready':
   motion['progress']['phase']='stopped';result['stopped']=True
  validate_world(e,W.actor_index(e))
  return result
 return G.transition(engine,actor,apply)
