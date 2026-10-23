"""The two printed Jump Kick miss exceptions use the actual Shield result."""
from copy import deepcopy
MOVES={'move/점프킥','move/무릎차기'}
def mechanics(r,mid,mm):
 if mid not in MOVES:return mm
 import priority_actions as P
 P._move(r,mid)
 result=deepcopy(mm)
 for effect in result.get('effects_exec',[]):
  if effect.get('type')=='hp_loss' and effect.get('on_miss') and effect.get('except')=='shield keyword miss':effect.pop('except')
 return result

def miss_effects(move,effects):
 if move.get('id') in MOVES and move.get('_shield_miss'):return [x for x in effects if not (x.get('type')=='hp_loss' and x.get('target')=='self' and x.get('on_miss'))]
 return effects
