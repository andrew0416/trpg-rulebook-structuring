"""Selected homebrew form state, distinct from permanent elemental choices."""
from copy import deepcopy
import state_fields as F
import world_entities as W
import personal_type_settings as PERSONAL
SOURCE='hb-terastal/테라스탈하는-방법'
KEY='terastal_state'

def _selected(r):
 if r._selected_rule(SOURCE)!=SOURCE:raise ValueError('selected Terastal source required')

def _type_value(c,value):
 if value is None:return None
 if not isinstance(value,str) or not value.strip():raise ValueError('exact nonempty Tera type identity required')
 if c.kind!='pokemon':raise ValueError('permanent Tera type belongs to Pokemon')
 if value==PERSONAL.TYPELESS:
  if not PERSONAL.enabled(c.r,'typeless_tera'):raise ValueError('personal typeless Terastal permission required')
  return value
 _selected(c.r)
 if value=='스텔라':
  if not any(x in ('스텔라버스트','ability/스텔라버스트') for x in c.abilities):raise ValueError('Stellar imitation requires the actual Stellar Blast ability')
 else:
  import type_state as TYPES
  TYPES.validate_types(c.r,[value],label='selected Tera type')
 return value

def tera_type(c):return _type_value(c,c.spec.get('tera_type'))

def _source(c,chosen):
 if chosen==PERSONAL.TYPELESS:
  _type_value(c,chosen)
  return PERSONAL.SOURCE
 _selected(c.r)
 return SOURCE

def validate(c):return _validate_record(c,c.spec.get(KEY),tera_type(c))

def _validate_record(c,row,chosen):
 if row is None:return True
 source=_source(c,chosen)
 required={'source','active','tera_type','original_stab_types','activated_at','origin','ended_reason'}
 if not isinstance(row,dict) or not required<=set(row) or set(row)-required-{'episode_id'}:raise ValueError('explicit Terastal state schema required')
 if row['source']!=source or type(row['active']) is not bool:raise ValueError('sourced boolean Terastal state required')
 if row['tera_type']!=chosen:raise ValueError('active-form receipt and permanent Tera type disagree')
 import type_state as TYPES
 if not isinstance(row['original_stab_types'],list):raise ValueError('explicit pre-transformation STAB types required')
 TYPES.validate_types(c.r,row['original_stab_types'],label='original Tera STAB types')
 from math import isfinite
 if isinstance(row['activated_at'],bool) or not isinstance(row['activated_at'],(int,float)) or not isfinite(row['activated_at']) or row['activated_at']<0:raise ValueError('actual activation time required')
 if not isinstance(row['origin'],dict) or not row['origin'].get('reason'):raise ValueError('actual state observation provenance required')
 return True

def tera_active(c):
 row=c.spec.get(KEY)
 if row is None:return False
 validate(c)
 # Native faint boundary also ends the stored receipt. Queries never resurrect it.
 return row['active'] and not c.fainted

def actual_types(c,ordinary):
 # Stellar preserves defense; it is neither Normal nor an empty type list.
 if not tera_active(c):return list(ordinary)
 chosen=c.spec[KEY]['tera_type']
 if chosen==PERSONAL.TYPELESS:return []
 return list(ordinary) if chosen=='스텔라' else [chosen]

def stab_types(c):
 import tera_shell as TERA_SHELL
 import type_state as TYPES
 ordinary=list(c.spec[KEY]['original_stab_types']) if tera_active(c) else list(c.types)
 if c.kind=='pokemon':ordinary=TYPES.source_stab_types(c.r,ordinary)
 return TERA_SHELL.stab_types(c,ordinary)

def ability_stab_types(c):
 values=stab_types(c)
 if tera_active(c) and c.spec['tera_type']!=PERSONAL.TYPELESS and c.spec['tera_type'] not in values:values.append(c.spec['tera_type'])
 return values

def effect_stab_types(c,e):
 # The optional rule extends ability predicates, not unrelated item/feature
 # predicates. Native ability registration supplies _ability provenance.
 return ability_stab_types(c) if e.get('_ability') else stab_types(c)

def type_change_blocked(c):return tera_active(c)

def damage_bonus(c,move,*,engine=None):
 import tera_shell as TERA_SHELL
 ordinary=10 if tera_active(c) and c.spec['tera_type']!=PERSONAL.TYPELESS and move.get('type')==c.spec['tera_type'] else 0
 return ordinary+TERA_SHELL.damage_bonus(c,move,engine=engine)

def observe_type(e,c,value,*,reason):
 """Record an established permanent choice, not acquisition permission."""
 W._text(reason,'Tera type observation reason')
 if W.actor_index(e).get(W.actor_id(c)) is not c:raise ValueError('actual world actor required')
 if tera_active(c):raise ValueError('end the current Terastal state before changing its permanent choice')
 _type_value(c,value)
 old=c.spec.get('tera_type');c.spec['tera_type']=value
 c.spec.pop(KEY,None)
 e.gm._rec('permanent Tera type',old,value,reason,c)
 return {'tera_type':value,'creation_legality_certified':False}

def observe_active(e,c,active,*,reason):
 """Source-bounded existing-form fact; activation action/cost remains separate."""
 W._text(reason,'Terastal observation reason')
 if type(active) is not bool:raise ValueError('explicit activation state required')
 if W.actor_index(e).get(W.actor_id(c)) is not c:raise ValueError('actual world actor required')
 chosen=tera_type(c)
 if chosen is None:raise ValueError('permanent Tera choice required before activation')
 if active and c.fainted:raise ValueError('conscious Pokemon required for active Terastal')
 old=deepcopy(c.spec.get(KEY))
 if active and tera_active(c):return deepcopy(old)
 if not active:
  if old is not None:end_active(c,reason=reason)
  return deepcopy(c.spec.get(KEY))
 source=_source(c,chosen)
 row={'source':source,'active':True,'tera_type':chosen,'original_stab_types':list(c.types),'activated_at':e.elapsed_seconds,'origin':{'source':'gm/observation','reason':reason,'activation_legality_certified':False},'ended_reason':None}
 _validate_record(c,row,chosen)
 import state_episodes as EPISODES
 row['episode_id']=EPISODES.start(c,family='terastal',source=source,native_ref={'field':KEY,'activated_at':e.elapsed_seconds})
 c.spec[KEY]=row
 e.gm._rec('active Terastal state',old,row,reason,c)
 return deepcopy(row)

def end_active(c,*,reason,episode_id=None):
 import state_episodes as EPISODES
 row=c.spec.get(KEY)
 if row is None:return
 if episode_id is not None and row.get('episode_id')!=episode_id:
  EPISODES.require(c,episode_id,family='terastal')
  return
 if not row.get('active'):return
 identity=row.get('episode_id')
 if identity is None:
  identity=EPISODES.start(c,family='terastal',source=row['source'],native_ref={'field':KEY,'activated_at':row['activated_at']})
  row['episode_id']=identity
 EPISODES.require(c,identity,family='terastal')
 def cleanup():row.update(active=False,ended_reason=reason)
 return EPISODES.end(c,identity,cause=reason,cleanup=cleanup)

def on_faint(c):
 row=c.spec.get(KEY)
 if row is not None and row.get('active') and c.fainted:end_active(c,reason='fainted')

def end_scene(e):
 for c in W.actors(e):
  row=c.spec.get(KEY)
  if row is not None and row.get('active'):end_active(c,reason='scene_end')

def preflight(e):
 for c in W.actors(e):validate(c)
 return True
