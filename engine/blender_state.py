"""Blender's source-owned camouflage uses the existing owner-turn clock."""
from copy import deepcopy
import state_grants as G,skill_modifiers as S,combat_timing as T
SOURCE='capability/녹아들기'


def records(actor):return [r for r in T.records(actor) if r.get('source')==SOURCE]


def validate(actor):
 rows=records(actor)
 if len(rows)>1:raise ValueError('Blender must not stack with itself')
 for row in rows:
  if actor.r._selected_rule(SOURCE)!=SOURCE:raise ValueError('selected Blender variant needs its own policy')
  if row.get('blender') is not True or row.get('turn_owner') is not actor or type(row.get('turn_deadline'))is not int or row['turn_deadline']<1 or row.get('encounter_end')is not True or row.get('effect_contract')is not True:raise ValueError('valid owner-turn Blender state required')
 return rows[0] if rows else None


def projection(actor):
 row=validate(actor)
 return {'active':row is not None,'matches_surroundings':row is not None,
         'melee_evasion':2 if row else 0,'ranged_evasion':4 if row else 0,
         'source':SOURCE if row else None,'ends_after_owner_turn':row['turn_deadline'] if row else None}


def activate(engine,actor,*,reason):
 import world_entities as W
 if W.actor_index(engine).get(actor.entity_id)is not actor:raise ValueError('actual registered Blender actor required')
 if not isinstance(reason,str) or not reason.strip():raise ValueError('explicit camouflage choice reason required')
 def apply(e,c):
  import turn as TURN
  if not e.encounter_active:raise ValueError('Blender next-turn lifetime requires an actual encounter clock')
  validate(c)
  if c.r._selected_rule(SOURCE)!=SOURCE:raise ValueError('selected Blender variant needs its own policy')
  if not {S.key('녹아들기'),S.key('Blender')}.intersection(S.key(x) for x in G.effective_capabilities(c)):raise ValueError('actual Blender capability required')
  if not TURN.spend(e,c,'shift','Blender camouflage'):raise ValueError('Blender Shift unavailable')
  before=deepcopy(projection(c))
  for old in list(records(c)):T.expire(e,c,old,ending='replaced')
  T.install(e,c,{'source':SOURCE,'blender':True,'effect_contract':True,'encounter_end':True,
                'turn_owner':c,'turn_deadline':c.custom_conditions.get('combat_turn_serial',0)+1,'reason':reason})
  e.gm._rec('Blender camouflage',before,projection(c),reason,c)
  return projection(c)
 return G.transition(engine,actor,apply)


def evasion(engine,actor,move):
 if validate(actor) is None:return 0
 import weapon_actions as WEAPONS
 origin=WEAPONS.range_spec(engine,move).get('origin')
 if origin=='melee':return 2
 if type(origin)is int and origin>0:return 4
 raise ValueError('Blender area attack needs a source-reviewed melee/ranged classification')
