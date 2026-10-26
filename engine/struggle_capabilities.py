"""Explicit per-attack elemental Struggle choices (ch10 named capabilities).

The shared Move definition is never changed; prepared moves retain the chosen
capability so accuracy and damage preparation revalidate the same declaration.
"""
from copy import deepcopy
import state_grants as G
import skill_modifiers as S

DEFINITIONS={
 '불쏘시개':('Firestarter','불꽃'), '물줄기':('Fountain','물'),
 '냉동고':('Freezer','얼음'), '세찬바람':('Guster','비행'),
 '구체화':('Materializer','바위'), '재퍼':('Zapper','전기'),
 '독샘':('Poison Glands','독'),
}
MARKER='_struggle_capability'


def canonical(value):
 for name,(english,_) in DEFINITIONS.items():
  if isinstance(value,str) and S.key(value) in {S.key(name),S.key(english),S.key('capability/'+name)}:return name
 raise ValueError('select one reviewed elemental Struggle capability')


def owned(actor,name):
 values=G.effective_capabilities(actor)
 return any(S.key(value) in {S.key(name),S.key(DEFINITIONS[name][0]),S.key('capability/'+name)} for value in values)


def prepare(engine,actor,move,choice=None):
 import ability_control_contracts as CONTROL
 move=CONTROL.prepare_move(engine,actor,move)
 selected=CONTROL.prepare_struggle(engine,actor,move,choice)
 if selected is not None:return selected
 created=move.get('innovation_instance')
 if created and created['template']==3 and move.get('id')!='struggle':
  import coordinator as COORDINATOR
  if COORDINATOR.innovation_instance(engine.r,move['id'])!=created:raise ValueError('actual Innovation Struggle identity changed')
  COORDINATOR.validate_spec(engine.r,actor.spec)
  original_id=move['id'];out=prepare(engine,actor,dict(move,id='struggle'),choice)
  # Native targets retain their live identities across repeated preparation.
  if '_actual_targets' in move:out['_actual_targets']=move['_actual_targets']
  return dict(out,id=original_id)
 import telekinetic_combat as TK
 if (move.get(TK.STRUGGLE_MARKER) is not None or
     isinstance(choice,dict) and S.key(choice.get('capability')) in {S.key(x) for x in ('염력','Telekinetic',TK.SOURCE)}):
  return TK.prepare_struggle(engine,actor,move,choice)
 previous=move.get(MARKER)
 if choice is None and previous is None:return move
 if choice is None:choice={'capability':previous.get('capability'),'special':previous.get('special')}
 if not isinstance(choice,dict) or set(choice)!={'capability','special'} or type(choice['special']) is not bool:
  raise ValueError('Struggle choice requires capability and boolean special')
 if move.get('id')!='struggle' or actor.kind not in ('pokemon','trainer') or move.get('_weapon_attack'):
  raise ValueError('elemental capability modifies an ordinary unarmed Struggle only')
 name=canonical(choice['capability']);source='capability/'+name
 if name!='독샘' and engine.r._selected_rule(source)!=source:raise ValueError('selected Struggle capability needs its own source policy')
 if not owned(actor,name):raise ValueError('actual Struggle capability required')
 expected={'source':source,'actor_id':actor.entity_id,'capability':name,'special':choice['special']}
 if previous is not None and previous!=expected:raise ValueError('prepared Struggle declaration changed')
 out=deepcopy(move);out['type']=DEFINITIONS[name][1];out['class']='특수' if choice['special'] else '물리';out[MARKER]=expected
 import ranged_struggle as RANGED
 reach=RANGED.range_for(actor,name)
 if reach is not None:
  out['_struggle_range']={'origin':reach,'targets':1,'raw':'6, 대상 1','parsed':True}
  out['range']='6, 대상 1'
 else:
  out.pop('_struggle_range',None);out['range']=engine.r.move('struggle')['range']
 return out
