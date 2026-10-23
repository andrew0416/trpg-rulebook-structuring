"""Sourced Aura Reader observations; no inferred alignment or mind reading."""
from copy import deepcopy
import common_checks as C
import state_grants as G
import skill_modifiers as S

KEY='aura_observation'
SOURCE='capability/파동-감지'
FIELDS=('color','personality','worldview','brightness','mood','intentions')


def _text(value,label):
 if not isinstance(value,str) or not value.strip():raise ValueError(label+' requires explicit descriptive text')
 return value


def validate(actor):
 row=actor.spec.get(KEY)
 if row is None:return None
 if not isinstance(row,dict) or row.get('source')!=SOURCE or row.get('target_id')!=actor.entity_id:raise ValueError('aura observation source/target mismatch')
 if not set(FIELDS)<=set(row):raise ValueError('all aura information fields must be explicit, including unknown values')
 if actor.r._selected_rule(SOURCE)!=SOURCE:raise ValueError('selected Aura Reader needs its own contract')
 C.integer(row.get('revision'),'aura observation revision',1)
 C.integer(row.get('at'),'aura observation time',0)
 if type(row.get('living')) is not bool:raise ValueError('observed living status required')
 _text(row.get('reason'),'aura observation reason')
 for key in FIELDS:
  if row.get(key) is not None:_text(row[key],'aura '+key)
 if row.get('brightness') not in (None,'bright','dark','neutral','mixed'):raise ValueError('explicit aura brightness description required')
 if row.get('color') is None and any(row.get(k) is not None for k in ('personality','worldview')):raise ValueError('personality insight requires its observed aura color')
 if row.get('brightness') is None and any(row.get(k) is not None for k in ('mood','intentions')):raise ValueError('mood/intention insight requires observed brightness')
 if not row['living'] and any(row.get(k) is not None for k in FIELDS):raise ValueError('nonliving observation cannot claim readable aura')
 return row


def _actual(engine,actor):
 import world_entities as W
 if W.actor_index(engine).get(actor.entity_id)is not actor:raise ValueError('actual registered aura participant required')


def observe(engine,target,*,living,color=None,personality=None,worldview=None,
            brightness=None,mood=None,intentions=None,reason):
 """GM records current descriptive information, never a universal color code.

Whole observations replace prior information explicitly; unknown fields stay
unknown. This does not grant a reader or expose unrelated target spec fields.
"""
 _actual(engine,target);old=validate(target)
 if target.dead and living is True:raise ValueError('dead target cannot be observed as currently living')
 row=dict(source=SOURCE,target_id=target.entity_id,revision=(old['revision'] if old else 0)+1,
          at=engine.elapsed_seconds,living=living,color=color,personality=personality,
          worldview=worldview,brightness=brightness,mood=mood,intentions=intentions,reason=reason)
 def apply(e,c):
  c.spec[KEY]=deepcopy(row);validate(c)
  e.gm._rec('aura observation',old,row,reason,c)
  return deepcopy(row)
 return G.transition(engine,target,apply)


def read(engine,reader,target):
 _actual(engine,reader);_actual(engine,target)
 if reader is target:raise ValueError('Aura Reader describes other living beings')
 names={S.key(x) for x in G.effective_capabilities(reader)}
 if not names.intersection(S.key(x) for x in ('파동 감지','Aura Reader',SOURCE)):raise ValueError('current Aura Reader capability required')
 if reader.r._selected_rule(SOURCE)!=SOURCE:raise ValueError('selected Aura Reader needs its own contract')
 row=validate(target)
 if target.dead or (row is not None and not row['living']):raise ValueError('living Aura Reader target required')
 if row is None:return C.PendingDecision('GM aura appearance and revealed information are not yet observed')
 if row['at']>engine.elapsed_seconds:raise ValueError('aura observation is from a future world time')
 import perception_observe as OBSERVE
 sensed=OBSERVE.observe(engine,reader,target,OBSERVE.native(SOURCE,('파동 감지','Aura Reader',SOURCE),provider='aura',information=FIELDS,mode='aura'))
 return {'source':SOURCE,'reader_id':reader.entity_id,'target_id':target.entity_id,
         'observation_revision':row['revision'],'observed_at':row['at'],
         'color_information':{key:sensed['values'][key] for key in ('color','personality','worldview')},
         'brightness_information':{key:sensed['values'][key] for key in ('brightness','mood','intentions')}}
