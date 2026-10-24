"""Double Team's three optional Coat activations (official core p395)."""
from copy import deepcopy
import common_checks as C
import effect_instances as E

SOURCE='move/그림자분신'
RAW={'type':'custom_condition','name':'그림자분신','on':'self','stacks':3,
 'effect':'consume one: +2 evasion when targeted by an attack, or +2 accuracy on own attack'}
COAT={'type':'apply_coat','coat':'그림자분신','target':'self','effect':{'activations':3}}
ROW={'raw':COAT,'payload':{'kind':'double_team_coat','blocks_push_pull':False},'lifetime':'until_spent_or_removed'}


def definition(rules,source):
 if source!=SOURCE:return None
 from source_context import verified_source
 verified_source(rules,{'file':'input/db/moves.csv','sha256':'ab83f872e5eca67a41db7d126b842f0165437e0fa70bb77ddad832a0b7396c93'},label='Double Team')
 if rules._selected_rule(source)!=source:raise ValueError('selected Double Team source changed')
 return ROW


def mechanics(rules,source,mechanics):
 if source!=SOURCE:return mechanics
 definition(rules,source)
 if mechanics.get('effects_exec')!=[RAW]:raise ValueError('reviewed Double Team declaration changed')
 return dict(mechanics,effects_exec=[deepcopy(COAT)])


def records(actor):
 return [row for row in actor.coats if isinstance(row,dict) and row.get('source')==SOURCE and E.KEY in row]


def validate(actor,record,terminal=False):
 E.validate(record,actor=actor,terminal=terminal);definition(actor.r,SOURCE)
 if record['effect']!=ROW['payload'] or record[E.KEY]['kind']!='coat' or record[E.KEY]['capacity']!={'bucket':'source_coat','source':SOURCE} or record[E.KEY]['lifetime']!={'boundary':ROW['lifetime']}:
  raise ValueError('actual Double Team Coat authority required')
 uses=record.get('applications')
 if type(uses) is not list or len(uses)>3:raise ValueError('three Double Team activations required')
 for use in uses:
  if set(use)!={'kind','holder_id','at'} or use['kind'] not in ('accuracy','evasion') or use['holder_id'] not in {event['holder_id'] for event in record[E.KEY]['ownership']}:
   raise ValueError('actual Double Team attack activation required')
  C.integer(use['at'],'Double Team use time',record['at'])
 if not terminal and len(uses)==3:raise ValueError('spent Double Team Coat remains live')
 if terminal:
  end=record[E.KEY]['end_event']
  if end=={'kind':'double_team_spent','actor_id':actor.entity_id}:
   if len(uses)!=3:raise ValueError('unspent Double Team archived as consumed')
  elif end.get('kind')!='coat_removed':raise ValueError('actual Double Team ending required')
 return True


def choose(engine,actor,mode,*,reason):
 import world_entities as W,coat_effects as COATS
 W.require_actors(engine,actor);COATS.validate_actor(actor)
 if mode not in ('accuracy','evasion') or not isinstance(reason,str) or not reason.strip():raise ValueError('explicit next actual attack activation required')
 if not records(actor):raise ValueError('actual unspent Double Team Coat required')
 actor.spec['double_team_choice']={'mode':mode,'reason':reason,'source':SOURCE}


def consume(engine,actor,mode,shared=None,*,opponent=None):
 if opponent is not None and __import__('oracle').sight(opponent):return 0
 key='double_team_accuracy'
 if mode=='accuracy' and shared is not None and key in shared:return shared[key]
 selection=actor.spec.get('double_team_choice')
 bonus=0
 if selection and selection.get('mode')==mode:
  rows=records(actor)
  if len(rows)!=1:raise ValueError('one actual Double Team Coat required')
  record=rows[0];validate(actor,record)
  record['applications'].append({'kind':mode,'holder_id':actor.entity_id,'at':engine.elapsed_seconds})
  actor.spec.pop('double_team_choice');bonus=2
  if len(record['applications'])==3:
   E.archive(engine,actor,record,state='consumed',event={'kind':'double_team_spent','actor_id':actor.entity_id});actor.coats.remove(record)
  engine.log(actor.name+': Double Team '+mode+' +2',SOURCE)
 if mode=='accuracy' and shared is not None:shared[key]=bonus
 return bonus
