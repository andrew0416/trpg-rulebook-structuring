"""Double Strike and Triple Kick use one native combined-damage activation."""
from copy import deepcopy
import common_checks as C
import root_resolution as R
KEY='multi_strike_history'

def kind(move):
 if '이단타격' in str(move.get('range','')):return 'double'
 if move.get('id')=='move/트리플킥':return 'triple'
 return None

def preflight(e,a,move):
 if kind(move) is None:return
 from source_context import verified_source
 import five_strike as F
 verified_source(e.r,F.SOURCE_REF,label='Double Strike source')
 import priority_actions as P
 if kind(P._move(e.r,move['id']))!=kind(move):raise ValueError('combined strike requires its actual printed keyword')

def mechanics(r,mid,mm):
 if mid not in r.moves:return mm
 move=r.move(mid);which=kind(move)
 if which is None:return mm
 import priority_actions as P
 P._move(r,mid)
 result=deepcopy(mm)
 result['effects_exec']=[x for x in result.get('effects_exec',[]) if x.get('type') not in ('multi_roll','conditional_damage_base')]
 result['effects_exec'].append({'type':'multi_roll','rolls':2 if which=='double' else 3,'crit_if_any_crit':which=='double'})
 return result

def record(e,a,t,move,results):
 which=kind(move)
 if which is None:return move
 preflight(e,a,move)
 row={'sequence':len(a.spec.get(KEY,[]))+1,'actor_id':a.entity_id,'target_id':t.entity_id,'move_id':move['id'],'kind':which,'rolls':[list(x) for x in results]}
 row['fingerprint']=R.fingerprint(row);a.spec.setdefault(KEY,[]).append(row)
 return dict(move,_multi_strike=deepcopy(row))

def observation(a,move):
 which=kind(move)
 if which is None:return None
 row=move.get('_multi_strike')
 if row is None or row not in a.spec.get(KEY,[]) or row['move_id']!=move['id']:raise ValueError('combined damage requires the actual native accuracy rolls')
 return row

def base(a,move,base):
 row=observation(a,move)
 if row is None:return base
 hits=sum(x[0] for x in row['rolls'])
 return base*hits if row['kind']=='double' else {0:0,1:1,2:3,3:6}[hits]

def separate_critical(move):return kind(move)=='double'

def critical_dice(e,a,move,set_damage):
 if not separate_critical(move):return 0
 row=observation(a,move);count=sum(hit and critical for hit,_,critical in row['rolls'])
 if not count:return 0
 base=e.r.move(move['id'])['damage_base'];entry=e.r.mech('combat/damage-chart')['by_damage_base'][str(base)]
 value=entry['set']['mid']*count if set_damage else e.roll_expr(entry['dice'],count)[0]
 e.log('    Double Strike: '+str(count)+' separately critical hit(s), printed DB '+str(base)+' -> '+str(value),'input/ch10-index-reference.md:298')
 return value

def validate(e):
 import world_entities as W
 index=W.actor_index(e)
 for a in index.values():
  for n,row in enumerate(a.spec.get(KEY,[]),1):
   facts={k:v for k,v in row.items() if k!='fingerprint'}
   if set(facts)!={'sequence','actor_id','target_id','move_id','kind','rolls'} or row['fingerprint']!=R.fingerprint(facts) or row['sequence']!=n or row['actor_id']!=a.entity_id or row['target_id'] not in index or kind(e.r.move(row['move_id']))!=row['kind']:raise ValueError('native multi-strike observation changed')
   if len(row['rolls'])!=(2 if row['kind']=='double' else 3):raise ValueError('multi-strike roll count changed')
   for hit,face,critical in row['rolls']:
    if type(hit) is not bool or type(critical) is not bool or critical and not hit:raise ValueError('actual multi-strike outcomes required')
    if face is not None:C.integer(face,'multi-strike natural d20',1,20)
