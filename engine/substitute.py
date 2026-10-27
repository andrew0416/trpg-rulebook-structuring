"""Core p410 Substitute: a source-owned Coat receives the actual incoming hit."""
import arithmetic_policy as NUMERIC
from copy import deepcopy
import common_checks as C
import effect_instances as E

SOURCE='move/대타출동'
RAW={'type':'apply_coat','coat':'대타출동','effect':{'decoy_hp':'lost hp + 1','absorbs_hits':True,'immune':['status','status moves']}}
ROW={'raw':RAW,'payload':{'kind':'substitute_coat','blocks_push_pull':False},'lifetime':'until_destroyed_or_removed'}


def definition(rules,source):
 if source!=SOURCE:return None
 from source_context import verified_source
 verified_source(rules,{'file':'input/db/moves.csv','sha256':'ab83f872e5eca67a41db7d126b842f0165437e0fa70bb77ddad832a0b7396c93'},label='Substitute Core p410 correction')
 if rules._selected_rule(source)!=source:raise ValueError('selected Core Substitute required')
 return ROW


def live(actor):return [r for r in actor.coats if isinstance(r,dict) and r.get('source')==SOURCE and E.KEY in r]


def project(e,actor,move,mechanics):
 if move['id']!=SOURCE:return mechanics
 definition(e.r,SOURCE)
 if actor.hp*4<actor.max_hp:raise ValueError('Substitute cannot be used below one quarter maximum HP')
 if live(actor):raise ValueError('actual Substitute Coat already exists')
 mm=deepcopy(mechanics)
 if mm.get('effects_exec')!=[{'type':'hp_loss','value':'max_hp/4','target':'self','unpreventable':True},RAW]:raise ValueError('reviewed Core Substitute extraction changed')
 mm['effects_exec']=[deepcopy(RAW)]
 return mm


def validate(actor,record,terminal=False):
 E.validate(record,actor=actor,terminal=terminal);definition(actor.r,SOURCE)
 if record['effect']!=ROW['payload'] or record[E.KEY]['capacity']!={'bucket':'source_coat','source':SOURCE} or record[E.KEY]['lifetime']!={'boundary':ROW['lifetime']}:raise ValueError('actual source-owned Substitute Coat required')
 basis=C.integer(record.get('maximum_hp'),'original Substitute HP basis',1)
 maximum=NUMERIC.ratio(basis,4)+1;remaining=C.integer(record.get('hp'),'actual Substitute HP',0,maximum)
 if record.get('paid_hp')!=NUMERIC.ratio(basis,4):raise ValueError('Substitute quarter HP payment changed')
 apps=record.get('applications')
 if type(apps)is not list:raise ValueError('actual Substitute hit observations required')
 previous=maximum
 for event in apps:
  C.integer(event.get('damage'),'Substitute incoming damage',0)
  if event.get('before')!=previous or event.get('after')!=max(0,previous-event['damage']):raise ValueError('Substitute hit HP observation changed')
  if not isinstance(event.get('actor_id'),str) or not isinstance(event.get('move_id'),str):raise ValueError('actual Substitute attack source required')
  previous=event['after']
 if previous!=remaining or not terminal and remaining<=0:raise ValueError('Substitute HP disagrees with actual hits')
 if terminal:
  end=record[E.KEY]['end_event']
  if end.get('kind')=='substitute_destroyed':
   if remaining!=0:raise ValueError('unbroken Substitute archived as destroyed')
  elif end.get('kind')!='coat_removed':raise ValueError('actual Substitute ending required')
 return True


def grant(e,actor,effect,source):
 if source!=SOURCE:return False
 if effect!=RAW:raise ValueError('actual Substitute Coat declaration required')
 if actor.hp*4<actor.max_hp or live(actor):raise ValueError('Substitute requires quarter HP and no existing Coat')
 basis=actor.max_hp;cost=NUMERIC.ratio(basis,4)
 # Core explicitly forbids every prevention layer, including temporary HP.
 e.lose_hp(actor,cost,source=SOURCE,unpreventable=True,loss_kind='hp_setting')
 record=E.create(e,actor,kind='coat',source=SOURCE,payload=ROW['payload'],capacity={'bucket':'source_coat','source':SOURCE},lifetime={'boundary':ROW['lifetime']},applied_by=actor)
 record.update(issued_turn=__import__('coat_effects').serial(actor),applications=[],maximum_hp=basis,paid_hp=cost,hp=cost+1)
 actor.coats.append(record);validate(actor,record)
 return True


def intercept(e,actor,target,move):
 if __import__('trickster').bypass(e,actor,target,move):return None
 rows=live(target)
 if not rows:return None
 import effects_ext as EXT,ability_transitions as A
 keywords=EXT.keywords_for(actor,move)
 if actor is target or keywords.intersection(('Social','Sonic','사회','소셜','사교','소리','음파')) or A.active(actor,'ability/틈새포착') or __import__('oracle').sight(actor):return None
 if len(rows)!=1:raise ValueError('one actual Substitute Coat required')
 row=rows[0];validate(target,row)
 return row


def receive_damage(e,actor,target,move,damage):
 row=intercept(e,actor,target,move)
 if row is None:return None
 before=row['hp'];row['hp']=max(0,before-damage)
 row['applications'].append({'actor_id':actor.entity_id,'holder_id':target.entity_id,'move_id':move['id'],'at':e.elapsed_seconds,'damage':damage,'before':before,'after':row['hp']})
 if not row['hp']:
  E.archive(e,target,row,state='consumed',event={'kind':'substitute_destroyed','actor_id':actor.entity_id,'move_id':move['id']});target.coats.remove(row)
 else:validate(target,row)
 return {'coat_id':row['id'],'damage':damage,'remaining_hp':row['hp']}


def mechanics(move,mechanics):
 """The actual native effect dispatcher still owns attacker effects and HP loss."""
 mm=deepcopy(mechanics)
 for key in ('apply_status','on_natural_roll','zone','evasion_mod','status','stage_changes'):mm.pop(key,None)
 mm['stage_changes_exec']=[x for x in mm.get('stage_changes_exec',[]) if x.get('target')=='self']
 mm['effects_exec']=[x for x in mm.get('effects_exec',[]) if x.get('target')=='self' or x.get('type')=='hp_loss' and move['class'] in ('물리','특수')]
 return mm


def toxic_mechanics(rules,mid,mechanics):
 if mid!='move/맹독':return mechanics
 mm=deepcopy(mechanics);mm.pop('never_miss',None)
 mm.setdefault('effects_exec',[])
 mm['effects_exec']=[effect for effect in mm['effects_exec'] if effect.get('type')!='never_miss']
 mm['effects_exec'].append({'type':'never_miss','if':'user is 독'})
 return mm
