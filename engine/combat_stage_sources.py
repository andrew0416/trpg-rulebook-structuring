"""Source-owned base CS and encounter CS; PTK limits apply to visible totals.

Created only on a reviewed base-stage producer. Other direct writers are not
reverse-engineered from clamped differences: snapshot disagreement is a hold.
"""
from copy import deepcopy
import common_checks as C
STATE='combat_stage_sources'
STATS=('atk','def','spa','spd','spe')

def limits(actor):return actor.r.mech('combat/combat-stages')['range']
def total(state,stat):return sum(x['deltas'].get(stat,0) for x in state['base'].values())
def render(actor,state):
 lo,hi=limits(actor)
 return {stat:max(lo,min(hi,state['combat'][stat]+total(state,stat))) for stat in STATS}
def validate(actor):
 # Refresh the one visible projection before capturing its source record.
 # Conditional getters may replace that record during this read.
 visible=actor.stages
 if not isinstance(visible,dict) or set(visible)!=set(STATS):raise ValueError('exactly five non-HP combat stages are required')
 lo,hi=limits(actor)
 for value in visible.values():C.integer(value,'visible combat stage',lo,hi)
 state=actor.spec.get(STATE)
 if state is None:return None
 if not isinstance(state,dict) or state.get('snapshot')!=visible:raise ValueError('untracked combat-stage writer requires explicit source reconciliation')
 if render(actor,state)!=visible:raise ValueError('base/combat stage source records disagree with actual stages')
 return state

def effective_stage(actor,stat):
 """Current CS for both Stat and movement consumers; never a final Stat value."""
 validate(actor)
 import capability_actions as CAPABILITIES
 import optional_state_effect_contracts as OPTIONAL_STATE
 import campaign_injury_policy as CAMPAIGN_INJURY
 stage=CAPABILITIES.speed_stage(actor) if stat=='spe' else actor.stages[stat]
 state=actor.spec.get(STATE)
 if state and any(row['source'].startswith('condition/') and __import__('blessing_effects').ignored(actor,row['source'].split('/',1)[1]) for row in state['base'].values()):
  raw=state['combat'][stat]+sum(row['deltas'].get(stat,0) for row in state['base'].values() if not (row['source'].startswith('condition/') and __import__('blessing_effects').ignored(actor,row['source'].split('/',1)[1])))
  lo,hi=limits(actor);stage=max(lo,min(hi,raw))
 stage+=OPTIONAL_STATE.combat_stage_delta(actor,stat)
 return max(-6,min(6,stage+CAMPAIGN_INJURY.stage_penalty(actor,stat)))

def prepared(actor):
 old=validate(actor)
 if old is not None:return deepcopy(old)
 # Existing passive CS must first be migrated by its real producer, not guessed
 # from a cap-limited registration delta.
 if any(any(v for v in row.get('stages',{}).values()) for row in getattr(actor,'_item_reg',{}).values()):raise ValueError('existing passive item CS requires native source import before herbal base CS')
 return {'base':{},'combat':dict(actor.stages),'snapshot':dict(actor.stages)}

def write(actor,state):
 visible=render(actor,state)
 # Publish values and their source snapshot together; do not re-enter a
 # conditional getter while the old source record is still installed.
 backing=vars(actor).get('stages')
 if isinstance(backing,dict):backing.clear();backing.update(visible)
 else:actor.stages=visible
 state['snapshot']=dict(visible);actor.spec[STATE]=state

def add_base(actor,key,stat,delta,*,source,ends):
 C.integer(delta,'base combat-stage delta')
 if stat not in STATS or not isinstance(key,str) or not key or not isinstance(source,str) or not source:raise ValueError('sourced base combat-stage producer required')
 state=prepared(actor)
 old=state['base'].get(key)
 if old is not None and (old['source']!=source or old['ends']!=ends):raise ValueError('base CS source identity cannot be replaced')
 record=state['base'].setdefault(key,{'source':source,'ends':ends,'deltas':{}})
 record['deltas'][stat]=record['deltas'].get(stat,0)+delta
 write(actor,state)

def change_combat(actor,stat,delta):
 import equipment_variant_contracts as EQUIPMENT_VARIANTS
 if getattr(actor,EQUIPMENT_VARIANTS.COVERT_BLOCK,None) is not None:return True
 state=validate(actor)
 if state is None:return False
 C.integer(delta,'combat-stage delta')
 state=deepcopy(state);lo,hi=limits(actor)
 # Ordinary CS effects act on the bounded current CS. The source-owned base
 # contribution remains intact so its own expiry never subtracts a guessed
 # effective delta from a capped value.
 desired=max(lo,min(hi,actor.stages[stat]+delta))
 if desired==actor.stages[stat]:return True  # a capped no-op must not erase hidden source offsets
 state['combat'][stat]=desired-total(state,stat)
 write(actor,state);return True

def prepare_assignment(actor,values):
 """Stage an explicit current-value edit without losing independent base sources."""
 if not isinstance(values,dict) or not values or not set(values)<=set(STATS):raise ValueError('only five non-HP combat stages can be assigned')
 lo,hi=limits(actor)
 for value in values.values():C.integer(value,'assigned combat stage',lo,hi)
 state=validate(actor)
 if state is None:return None,dict(values)
 state=deepcopy(state)
 for stat,value in values.items():
  if value!=actor.stages[stat]:state['combat'][stat]=value-total(state,stat)
 return state,dict(values)

def commit_assignment(actor,assignment):
 state,values=assignment
 if state is None:actor.stages.update(values)
 else:write(actor,state)

def assign_combat(actor,values):
 commit_assignment(actor,prepare_assignment(actor,values))

def end_encounter(actor):
 state=validate(actor)
 if state is None:return False
 state=deepcopy(state);state['combat']={stat:0 for stat in STATS};write(actor,state);return True

def end_source(actor,*,ends):
 state=validate(actor)
 if state is None:return
 state=deepcopy(state);state['base']={k:v for k,v in state['base'].items() if v['ends']!=ends};write(actor,state)
