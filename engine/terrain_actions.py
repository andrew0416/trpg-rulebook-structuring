"""Groundshaper changes selected cardinal body-neighbor cells in one action."""
from copy import deepcopy
import state_grants as G
import state_fields as F
SOURCE='capability/지형변화'
HISTORY='groundshaper_history'
TERRAINS={'rough':(True,False),'slow':(False,True),'both':(True,True),'normal':(False,False)}


def point(value):
 if not isinstance(value,(tuple,list)) or len(value)!=2:raise ValueError('terrain cell must be a coordinate pair')
 return tuple(F.integer(x,'terrain coordinate') for x in value)


def validate_history(actor):
 rows=actor.spec.get(HISTORY,[])
 if not isinstance(rows,list):raise ValueError('terrain action history must be a list')
 for n,row in enumerate(rows,1):
  if not isinstance(row,dict) or set(row)-{'type_ace'}!={'sequence','source','actor_id','action','seconds','reason','body_cells','changes'}:raise ValueError('exact terrain action receipt required')
  if type(row['sequence']) is not int or row['sequence']!=n or row['source']!=SOURCE or row['actor_id']!=actor.entity_id or row['action']!=('free' if 'type_ace' in row else 'standard'):raise ValueError('terrain action identity mismatch')
  F.integer(row['seconds'],'terrain observation time',0)
  if not isinstance(row['reason'],str) or not row['reason'].strip():raise ValueError('terrain observation reason required')
  if not isinstance(row['body_cells'],list) or not row['body_cells']:raise ValueError('actual body cells required')
  body={point(x) for x in row['body_cells']};seen=set()
  ace=row.get('type_ace')
  if ace is not None:
   if type(ace)is not dict or set(ace)!={'feature','completion_id','allowed_cells'} or ace['feature']!=__import__('type_ace').uid('Mold the Earth'):raise ValueError('actual Type Ace terrain source required')
   allowed={point(x) for x in ace['allowed_cells']}
  if not isinstance(row['changes'],list) or not row['changes']:raise ValueError('nonempty terrain change receipt required')
  for change in row['changes']:
   if not isinstance(change,dict) or set(change)!={'cell','terrain','before','after'}:raise ValueError('exact terrain cell change required')
   cell=point(change['cell'])
   if cell in seen or (cell not in allowed if ace is not None else cell in body or not any(abs(cell[0]-x)+abs(cell[1]-y)==1 for x,y in body)):raise ValueError('terrain cell must have been cardinally adjacent')
   seen.add(cell)
   for field in ('before','after'):
    if not isinstance(change[field],dict) or set(change[field])!={'rough','slow'} or any(type(x)is not bool for x in change[field].values()):raise ValueError('explicit terrain flags required')
   if change['terrain'] not in TERRAINS or tuple(change['after'][k] for k in ('rough','slow'))!=TERRAINS[change['terrain']]:raise ValueError('terrain change disagrees with selected kind')
   if change['terrain']=='normal' and not change['before']['rough']:raise ValueError('normalization requires previously Rough terrain')
 return True


def shape(engine,actor,changes,*,reason):
 import world_entities as W
 if W.actor_index(engine).get(actor.entity_id) is not actor:raise ValueError('actual registered Groundshaper required')
 if engine.grid is None:raise ValueError('Groundshaper requires an actual map')
 if not isinstance(changes,(list,tuple)) or not changes:raise ValueError('select at least one terrain cell')
 if not isinstance(reason,str) or not reason.strip():raise ValueError('terrain change reason required')
 def apply(e,c):
  import body_state as BODY,turn as TURN
  validate_history(c)
  if e.r._selected_rule(SOURCE)!=SOURCE:raise ValueError('selected Groundshaper requires its own policy')
  ace=__import__('type_ace').terrain_scope(e,c)
  names={str(x).removeprefix('capability/') for x in G.effective_capabilities(c)}
  if ace is None and not names.intersection(('지형변화','Groundshaper')):raise ValueError('actual Groundshaper capability required')
  body=BODY.cells(c,require_complete=True);rows=[]
  for change in changes:
   if not isinstance(change,dict) or set(change)!={'cell','terrain'}:raise ValueError('select cell and terrain only')
   cell=point(change['cell']);kind=change['terrain']
   if not e.grid.inside(cell) or kind not in TERRAINS:raise ValueError('on-map reviewed terrain kind required')
   rows.append({'cell':list(cell),'terrain':kind,'before':{'rough':cell in e.grid.rough,'slow':cell in e.grid.slow},'after':dict(zip(('rough','slow'),TERRAINS[kind]))})
  receipt={'sequence':len(c.spec.get(HISTORY,[]))+1,'source':SOURCE,'actor_id':c.entity_id,'action':'standard','seconds':e.elapsed_seconds,'reason':reason,'body_cells':[list(x) for x in sorted(body)],'changes':rows}
  if ace is not None:receipt.update(action='free',type_ace={k:deepcopy(ace[k]) for k in ('feature','completion_id','allowed_cells')})
  c.spec.setdefault(HISTORY,[]).append(receipt);validate_history(c)
  if not TURN.spend(e,c,'free' if ace is not None else 'standard','Groundshaper'):raise ValueError('Groundshaper Standard action unavailable')
  for change in rows:
   cell=tuple(change['cell'])
   for name in ('rough','slow'):
    if change['after'][name]:getattr(e.grid,name).add(cell)
    else:getattr(e.grid,name).discard(cell)
  e.gm._rec('Groundshaper terrain',None,deepcopy(receipt),reason,c)
  return receipt
 # The common actor transaction stages validation, callbacks, action cost and receipt.
 # Grid is intentionally not a field committed by that transaction. Publish the
 # validated cell patch afterwards, preserving the live Grid and set identities.
 receipt=G.transition(engine,actor,apply)
 for row in receipt['changes']:
  cell=tuple(row['cell'])
  for name in ('rough','slow'):
   target=getattr(engine.grid,name)
   if row['after'][name]:target.add(cell)
   else:target.discard(cell)
 return deepcopy(receipt)
