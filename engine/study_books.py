"""May/September 2015 Books: physical text, sequential study and temporary consumers.

Books are not permanent acquired Edges. Native consumers ask this owner for a
current benefit; AP and Study Point recovery remain owned by their native ledgers.
"""
from copy import deepcopy
from contextlib import contextmanager
import common_checks as C
import skill_modifiers as S
import state_grants as G
import world_entities as W

KEY='study_books'
OBJECT='study_book'
SOURCE='input/supp-errata.md:268-437'
MAY_SHA='b1314908e4adbfee09042c58f08a36046b5f59a09de196425aa469b43232232d'
SEP_SHA='846c23a90f26d7deb7a86117622378bc60dc7c729a9a6b1e747ea67d4a1c6caf'
KR_SHA='90e533bde766c6ffe8fb480dd8e2478e5fddf3ed1fef9a7a1032070245622a3e'
CORE_SHA='e5e0371031601c3ad0a04056771c17599a2d8826e5a5102ccd37f9b368108907'
POLYGON_SHA='a77531bf881aecca0311ecc7be85f579f275e8016a1be1b75761360ad02d6594'
ITEMS=dict(zip(('study_manual','joy_cooking','berries','first_aid','traditional_medicine','caretaker','dowsing','spooked','tinfoil','type_manual','daycare','fishing','fungi','travel','anarchist','ball_manual','diy','combat_medic'),
 ('공부-메뉴얼','요리의-즐거움','베리에-대하여','응급처치-메뉴얼','전통의학-참조서','관리-메뉴얼','바보도-따라하는-다우징','겁먹지-않는-법','틴포일-복음서-새로운-세계-질서의-정신에-대한-입문서','타입-공부-메뉴얼','포켓몬-돌보미-라이센스-가이드','낚시-101','균류-현장-가이드','여행-가이드','아나키스트-요리책','몬스터볼-전문-메뉴얼','diy-엔지니어링','전투-메딕의-기본-지침서')))
ITEMS={k:'item/'+v for k,v in ITEMS.items()}
# book: (printed skill, rank-one threshold, rank-two threshold, literal KR span)
BOOKS={
 'study_manual':('일반 지식',3,5,[280,288]),
 'joy_cooking':('일반 지식',3,5,[290,296]),
 'berries':('일반 지식',4,5,[298,304]),
 'first_aid':('의학',3,5,[308,314]),
 'traditional_medicine':('의학',4,5,[316,324]),
 'caretaker':('의학',4,6,[326,332]),
 'dowsing':('오컬트학',3,4,[336,342]),
 'spooked':('오컬트학',4,5,[344,350]),
 'tinfoil':('오컬트학',3,5,[352,362]),
 'type_manual':('포켓몬학',3,5,[366,372]),
 'daycare':('포켓몬학',4,6,[374,380]),
 'fishing':('생존',3,4,[386,392]),
 'fungi':('생존',3,4,[394,400]),
 'travel':('생존',3,5,[402,408]),
 'anarchist':('기술학',3,5,[412,418]),
 'ball_manual':('기술학',3,5,[420,426]),
 'diy':('기술학',3,5,[428,432]),
 'combat_medic':('의학',3,5,[685,695]),
}


def _hash(value):
 return __import__('resolution_transaction').request_fingerprint(value)


def authority(rules,book,edition):
 if book not in BOOKS:raise ValueError('reviewed Study Book required')
 allowed=('sep2015',) if book=='combat_medic' else ('may2015','korean') if book=='spooked' else ('may2015',)
 if edition not in allowed:raise ValueError('reviewed Book source choice required')
 from source_context import verified_source
 if rules._selected_rule(ITEMS[book])!=ITEMS[book]:raise ValueError('selected Book needs its reviewed source adapter')
 verified_source(rules,{'file':'input/supp-errata.md','sha256':KR_SHA},label='Korean Book source')
 path='source-audit/official-sep2015.pdf' if book=='combat_medic' else 'source-audit/official-may2015.pdf'
 digest=SEP_SHA if book=='combat_medic' else MAY_SHA
 ref={'file':path,'sha256':digest}
 verified_source(rules,ref,label='Study Books',source_root='source-audit')
 return dict(ref,edition=edition,clause_id=SOURCE if book!='combat_medic' else 'input/supp-errata.md:685-695',span=BOOKS[book][3])


def epoch(actor):
 import recovery_receipts as R
 return sorted(uid for uid,row in R.validate(actor).items()
  if row['intent'].get('source')=='gameplay/action-points' and row['intent'].get('resource')=='ap_removed'
  and row['intent'].get('policy')=='qualified_extended_rest' and row['eligibility'].get('eligible'))


def _details(rules,book,value):
 if type(value)is not dict:raise ValueError('exact physical Book selection required')
 keys={'study_manual':{'skill','use'},'type_manual':{'type'},'daycare':{'egg_group'},'travel':{'region'}}.get(book,set())
 if set(value)!=keys:raise ValueError('exact Book-specific selection required')
 for v in value.values():G._text(v,'Book selection')
 if book=='study_manual':S.skill_id(rules.skill_policy,value['skill'],required=True)
 if book=='type_manual' and value['type'] not in __import__('items').TYPES:raise ValueError('actual canonical studied Type required')
 if book=='daycare':
  groups={g for row in rules.species.values() for g in row.get('egg_groups',row.get('egg_group',[]))}
  if value['egg_group'] not in groups:raise ValueError('actual source Egg Group required')
 return deepcopy(value)


def observe(engine,owner,instance_id,book,*,details,reason,edition=None,weight_kg=1):
 """GM observation of one real text; neither purchase nor inventory duplication."""
 W.require_actors(engine,owner);G._text(reason,'actual physical Book observation')
 if owner.kind!='trainer':raise ValueError('actual Trainer Book reader required')
 edition=edition or ('sep2015' if book=='combat_medic' else 'may2015')
 auth=authority(engine.r,book,edition);selection=_details(engine.r,book,details)
 if instance_id in W.entity_index(engine):raise ValueError('fresh physical Book identity required')
 def apply(e,t):
  W.register_object(e,instance_id,location=W.location_of(t),reason=reason,owner_id=t.entity_id,weight_kg=weight_kg,source=ITEMS[book],kind='item_instance',item_rule_id=ITEMS[book])
  record={'book':book,'details':selection,'authority':auth,'reason':reason}
  e._physical_objects[instance_id][OBJECT]=dict(record,integrity=_hash(record))
  return deepcopy(e._physical_objects[instance_id])
 return G.transition(engine,owner,apply)


def _object(engine,actor,instance_id):
 obj=getattr(engine,'_physical_objects',{}).get(instance_id)
 if type(obj)is not dict or OBJECT not in obj:raise ValueError('actual registered physical Study Book required')
 W.require_usable_object(obj)
 row=obj[OBJECT];body={k:v for k,v in row.items() if k!='integrity'}
 if row.get('integrity')!=_hash(body):raise ValueError('physical Book text changed')
 if row['authority']!=authority(engine.r,row['book'],row['authority']['edition']):raise ValueError('Book authority changed')
 _details(engine.r,row['book'],row['details'])
 if obj.get('owner_id')!=actor.entity_id:raise ValueError('actual owned Book required for study')
 carrier=obj.get('carrier_id') or obj.get('equipped_by')
 if carrier and carrier!=actor.entity_id:raise ValueError('Book is carried by another actor')
 if not carrier and W.location_of(obj)!=W.location_of(actor):raise ValueError('actual Book must be within reach for study')
 return row


def _state(actor,create=False):
 value=actor.spec.get(KEY)
 if value is None:return actor.spec.setdefault(KEY,{'studies':[],'withdrawn':[],'events':[]}) if create else {'studies':[],'withdrawn':[],'events':[]}
 if type(value)is not dict or set(value)!={'studies','withdrawn','events'} or any(type(x)is not list for x in value.values()):raise ValueError('exact Study Book state required')
 return value


def rows(actor,book=None,rank=1):
 """Read-only current effects; an actual AP-rest receipt expires every old rank."""
 st=_state(actor);current=epoch(actor);found=[]
 for row in st['studies']:
  if row.get('integrity')!=_hash({k:v for k,v in row.items() if k!='integrity'}):raise ValueError('Book study receipt changed')
  if book is not None and row['book']!=book:continue
  if row['authority']!=authority(actor.r,row['book'],row['authority']['edition']):raise ValueError('studied Book authority changed')
  if row['rest_epoch']==current and row['source_id'] not in st['withdrawn'] and (book is None or row['book']==book) and row['rank']>=rank:found.append(row)
 # Rank two is never an independent effect after rank one was withdrawn.
 live_one={r['instance_id'] for r in st['studies'] if r['rank']==1 and r['rest_epoch']==current and r['source_id'] not in st['withdrawn']}
 return [r for r in found if r['rank']==1 or r['instance_id'] in live_one]


def active(actor,book,rank=1):return bool(rows(actor,book,rank))


def _qualify(engine,actor,book,rank,edition):
 skill,one,two,_=BOOKS[book];required=(one,two)[rank-1]
 if book=='spooked' and edition=='korean':required-=1
 actual=S.rank(engine.r,actor,skill)[2]
 if actual>=required:return
 import researcher_fields as RFS
 if actual>=3 and RFS.owns(actor,'feat/이해-완료'):
  RFS.qualify(engine,actor,'feat/이해-완료',available=False)
  if S.rank(engine.r,actor,'일반 지식')[2]>=required:return
 raise ValueError('Book rank requires its printed Skill or qualified Well Read')


def study(engine,actor,instance_id,rank,*,payment='ap',during_rest=False,reason):
 """Exactly 30 minutes and one native Drain per sequential physical Book rank."""
 W.require_actors(engine,actor);G._text(reason,'Book study reason');C.integer(rank,'Book rank',1,2)
 if engine.encounter_active:raise ValueError('Book study requires outside-combat Extended Action')
 if payment not in ('ap','study'):raise ValueError('AP or Bookworm Study Point payment required')
 physical=_object(engine,actor,instance_id);book=physical['book'];edition=physical['authority']['edition']
 _qualify(engine,actor,book,rank,edition)
 owned=[r for r in rows(actor) if r['instance_id']==instance_id]
 prior=max((r['rank'] for r in owned),default=0)
 if rank!=prior+1:raise ValueError('Book ranks must be gained sequentially without duplicate Drain')
 if book=='caretaker' and rank==2 and during_rest is not True:raise ValueError('Caretaker rank two can only be studied while taking an Extended Rest')
 if during_rest and (book!='caretaker' or rank!=2):raise ValueError('only Caretaker rank two binds during Extended Rest')
 import action_points as AP
 if payment=='ap' and not during_rest and AP.available(actor)<1:raise ValueError('one available AP required for Book Drain')
 if payment=='study':__import__('researcher_fields').study_points(engine,actor)
 def apply(e,t):
  import turn as TURN
  st=_state(t,True);sid='study-book:'+t.entity_id+':'+str(len(st['studies'])+1)
  if not TURN.spend(e,t,'extended',SOURCE):raise ValueError('Book study Extended Action unavailable')
  e.advance_time(1800,[t],source=SOURCE)
  if not during_rest:
   if payment=='ap':AP.charge(t,1,mode='drain')
   else:__import__('researcher_fields')._drain_study(e,t,sid)
  body={'source_id':sid,'instance_id':instance_id,'book':book,'rank':rank,'details':deepcopy(physical['details']),
    'authority':deepcopy(physical['authority']),'rest_epoch':epoch(t),'payment':payment,'at':e.elapsed_seconds,'during_rest':during_rest,'reason':reason}
  row=dict(body,integrity=_hash(body));st['studies'].append(row)
  return deepcopy(row)
 return G.transition(engine,actor,apply,include_rulings=True)


def withdraw(engine,actor,source_id):
 """Explicitly end a temporary benefit, never refund a printed Drain."""
 paid={r['provider']['study']['source_id'] for r in _state(actor)['events'] if r.get('event')=='caretaker' and r['paid_after_rest'] and r['paid_epoch']==epoch(actor)}
 if source_id not in ({r['source_id'] for r in rows(actor)}|paid) or source_id in _state(actor)['withdrawn']:raise ValueError('actual live Book source required')
 def apply(e,t):
  st=_state(t,True);row=next(r for r in st['studies'] if r['source_id']==source_id)
  ids=[r['source_id'] for r in rows(t) if r['instance_id']==row['instance_id'] and r['rank']>=row['rank']]
  if not ids:ids=[source_id]
  st['withdrawn'].extend(ids);return source_id
 return G.transition(engine,actor,apply)


def _owner(engine,target,book,rank=1):
 owner=target if target.kind=='trainer' else W.actor_index(engine).get(target.spec.get('trainer_id'))
 return owner if owner is not None and active(owner,book,rank) else None


def stunts(engine,actor):
 result=[]
 for row in rows(actor):
  if row['rank']!=1:continue
  choices=[];book=row['book'];d=row['details']
  if book=='study_manual':choices=[(d['skill'],d['use'])]
  elif book=='tinfoil':choices=[('집중','resisting Telepathy')]
  elif book=='travel' and region(actor)==d['region']:choices=[('생존','Foraging'),('생존','Navigation')]
  for i,(skill,use) in enumerate(choices):result.append({'id':row['source_id']+'/'+str(i),'skill':skill,'skill_id':S.skill_id(engine.r.skill_policy,skill,required=True),'use':use,'gm_approved':True,'approval_reason':row['reason'],'source':row['source_id']})
 return result


def manual_bonus(actor,skill,equipment_bonus=0):
 """One nonstacking Books/Equipment group; ordinary feat bonuses stay outside."""
 canonical=S.skill_id(actor.r.skill_policy,skill,required=True)
 benefit=any(S.skill_id(actor.r.skill_policy,r['details']['skill'],required=True)==canonical for r in rows(actor,'study_manual',2))
 return max(equipment_bonus,2 if benefit else 0)


def iron_mind(actor):return active(actor,'tinfoil')


def first_aid_bonus(actor):return 10 if active(actor,'first_aid') else 0


def first_aid_expertise(engine,actor,target):
 """Book's single daily use delegates the shared actual First Aid recovery."""
 if not active(actor,'first_aid',2):raise ValueError('actual rank-two First Aid Manual required')
 import class_actor_state_actions as A
 return A.emergency_care(engine,actor,target,book_provider=True)


def herbal(engine,user,target):
 return {'ignore_cs_loss':active(user,'traditional_medicine'),
         'repeat_food_buff':active(user,'traditional_medicine',2)}


def fungi(engine,actor):return _owner(engine,actor,'fungi') is not None


def fungi_identifies(actor):return active(actor,'fungi')


def region(actor):
 fact=actor.spec.get('crafting_location')
 if fact is None:return None
 if type(fact)is not dict or set(fact)!={'region','source','reason'}:raise ValueError('actual sourced region observation required')
 for v in fact.values():G._text(v,'actual region observation')
 return fact['region']


def natural_weather_immune(engine,actor):
 import weather_state as WEATHER
 weather=WEATHER.effective_state(engine,actor,include_virtual=False).get('active')
 if not weather or weather.get('origin')!='natural':return False
 owner=_owner(engine,actor,'travel',2)
 return owner is not None and any(r['details']['region']==region(actor) for r in rows(owner,'travel',2))


def _cleanse_hand(engine,actor):
 import items as I,held_equipment as H
 hands={'주요손','반대손'}
 held={r.get('instance_id') for r in H.entries(actor) if r['slot_id'] in hands}
 return any(r.get('item_id') in ('item/순결의부적','item/순결의부적-1') and (set(r.get('slots',[])).intersection(hands) or r.get('instance_id') in held) and I.equipment_benefit_active(actor,r) for r in getattr(actor,'_item_reg',{}).values())


def sees_invisible(engine,actor):return active(actor,'spooked') and _cleanse_hand(engine,actor)


def cursed_immune(engine,actor):return active(actor,'spooked',2) and _cleanse_hand(engine,actor)


def _event(actor,event,*,scope='day',target=None):
 period=actor.spec.get('frequency_state',{}).get(scope,0)
 key={'event':event,'scope':scope,'period':period,'target':target}
 return key,any(all(row.get(k)==v for k,v in key.items()) for row in _state(actor)['events'])


def yield_bonus(engine,actor,*,use,production_id=None):
 if type(use)is not bool:raise ValueError('explicit How Berries daily bonus choice required')
 if not use:return 0
 if not active(actor,'berries'):raise ValueError('actual How Berries rank one required')
 key,spent=_event(actor,'berries_yield')
 if spent:raise ValueError('How Berries yield bonus already used today')
 _state(actor,True)['events'].append(dict(key,production_id=production_id));return 1


def dowsing_plan(engine,actor,rank,used,color):
 import crafting_resources as R
 if color is not None:
  if not active(actor,'dowsing',2) or color not in R.SHARDS:raise ValueError('rank-two Book and canonical Shard Color required')
 uses=2 if color is not None else 1
 if used+uses>__import__('arithmetic_policy').ratio(rank,2):raise ValueError('insufficient daily Dowsing activations for chosen color')
 return {'dice':int(active(actor,'dowsing')),'uses':uses,'color':color}


def type_capture(actor,target):
 return -5 if any(r['details']['type'] in target.types for r in rows(actor,'type_manual')) else 0


def training_bonus(engine,actor,targets,selected):
 """Called inside the actual Experience Training transaction, once per day."""
 if selected is None:return None
 if selected not in targets or selected.kind!='pokemon' or selected.spec.get('trainer_id')!=actor.entity_id:raise ValueError('one actual owned training participant required')
 if not any(r['details']['type'] in selected.types for r in rows(actor,'type_manual',2)):raise ValueError('rank-two studied Type training target required')
 key,used=_event(actor,'type_manual_xp')
 if used:raise ValueError('Type Study Manual bonus already applied today')
 previous=[r for r in _state(actor)['events'] if r.get('event')=='type_manual_xp' and r.get('period')==key['period']-1]
 if any(r.get('pokemon_id')==selected.entity_id for r in previous):raise ValueError('same Pokemon cannot receive Type Study Manual bonus on consecutive days')
 __import__('downtime').gain_exp_combatant(engine,selected,10)
 _state(actor,True)['events'].append(dict(key,pokemon_id=selected.entity_id))
 return {'pokemon_id':selected.entity_id,'bonus_xp':10}


def daycare(actor,egg_group,rank=1):
 return any(r['details']['egg_group']==egg_group for r in rows(actor,'daycare',rank))


def fished(engine,actor,target,stats):
 if stats is None:
  if active(actor,'fishing',2):raise ValueError('Fishing 101 requires its two Combat Stat choices when landing a Pokemon')
  _state(actor,True)['events'].append({'event':'fished','pokemon_id':target.entity_id});return
 if not active(actor,'fishing',2):raise ValueError('rank-two Fishing 101 required')
 if type(stats)is not list or len(stats)!=2 or len(set(stats))!=2 or any(s not in ('atk','def','spa','spd','spe') for s in stats):raise ValueError('two distinct actual Combat Stats required')
 _state(actor,True)['events'].append({'event':'fished','pokemon_id':target.entity_id})
 for stat in stats:engine.change_stage(target,stat,-1)
 engine.apply_status(target,'풀죽음',source=SOURCE)


def fishing_snare(actor,target):
 return active(actor,'fishing') and any(r.get('event')=='fished' and r.get('pokemon_id')==target.entity_id for r in _state(actor)['events'])


def joy_recipe_value(actor,amount,evidence):
 """The paid native receipt may retain its original reader after study expires."""
 if evidence is None:return amount
 if type(evidence)is not dict or set(evidence)!={'owner_id','study'}:raise ValueError('actual recipe discount Book provider required')
 row=evidence['study']
 if evidence['owner_id']!=actor.entity_id or row not in _state(actor)['studies'] or row.get('book')!='joy_cooking' or row.get('rank',0)<1:raise ValueError('recipe discount lost its actual reader')
 if row.get('integrity')!=_hash({k:v for k,v in row.items() if k!='integrity'}):raise ValueError('recipe discount Book provider changed')
 return __import__('arithmetic_policy').ratio(amount*9,10)


def recipe(engine,actor,value):
 """Native recipe owner calls once before material planning; never reduces counts."""
 value=deepcopy(value)
 for group in value['materials']:
  for option in group['options']:
   if option['kind']!='value':continue
   category=option['category']
   qualifies=(category=='음식' and active(actor,'joy_cooking')) or (category=='몬스터볼' and active(actor,'ball_manual')) or (category in ('기계','기계 파편','mechanical') and active(actor,'diy'))
   if qualifies:option['amount']=__import__('arithmetic_policy').ratio(option['amount']*9,10)
 return value


def anarchist(engine,user,target,*,repel,hit):
 """Called only after the native Repel/Pester Ball producer's actual result."""
 if not active(user,'anarchist'):return None
 out={'blinded':False,'hp_loss':0}
 if repel:
  key,used=_event(user,'anarchist_blind',scope='scene',target=target.entity_id)
  if not used:
   import effect_lifetimes as L,combat_timing as T
   record=L.prepare(engine,user,target,{'type':'apply_status','status':'실명','until':"end of target's next turn"},SOURCE)
   record['statuses']=['실명'];T.install(engine,target,record)
   _state(user,True)['events'].append(key);out['blinded']=True
 if hit and active(user,'anarchist',2):
  amount=S.rank(engine.r,user,'기술학')[2];before=target.hp
  engine.lose_hp(target,amount,source=SOURCE);out['hp_loss']=before-target.hp
 return out


def renew(engine,actor,source_ids,*,payment='ap',reason):
 """After actual rest, choose former Drains to renew without studying again."""
 W.require_actors(engine,actor);G._text(reason,'Book renewal choice')
 if type(source_ids)is not list or not source_ids or len(set(source_ids))!=len(source_ids):raise ValueError('distinct actual former Book ranks required')
 prior={r['source_id']:r for r in _state(actor)['studies']}
 if any(sid not in prior or prior[sid]['rest_epoch']==epoch(actor) for sid in source_ids):raise ValueError('actual expired Book Drains required for renewal')
 chosen=[prior[sid] for sid in source_ids]
 latest={(r['instance_id'],r['rank']):r['source_id'] for r in prior.values()}
 if any(r['source_id']!=latest[(r['instance_id'],r['rank'])] for r in chosen):raise ValueError('latest former Book rank required')
 if any(any(x['instance_id']==r['instance_id'] and x['rank']==r['rank'] for x in rows(actor)) for r in chosen):raise ValueError('Book rank already renewed')
 for row in chosen:
  if row['rank']==2 and not any(x['instance_id']==row['instance_id'] and x['rank']==1 for x in chosen):raise ValueError('renewed Book rank two also requires renewing rank one')
  _qualify(engine,actor,row['book'],row['rank'],row['authority']['edition'])
 if payment not in ('ap','study'):raise ValueError('actual Book renewal payment required')
 def apply(e,t):
  import action_points as AP
  out=[];st=_state(t,True)
  for former in sorted(chosen,key=lambda x:x['rank']):
   sid='study-book:'+t.entity_id+':'+str(len(st['studies'])+1)
   if not former.get('during_rest'):
    if payment=='ap':AP.charge(t,1,mode='drain')
    else:__import__('researcher_fields')._drain_study(e,t,sid)
   body=dict(former,source_id=sid,rest_epoch=epoch(t),payment=payment,at=e.elapsed_seconds,reason=reason)
   body.pop('integrity');row=dict(body,integrity=_hash(body));st['studies'].append(row);out.append(deepcopy(row))
  return out
 return G.transition(engine,actor,apply,include_rulings=True)


def aura_information(engine,reader,target,information,*,reader_skill=None,target_skill=None,reader_roll=None,target_roll=None):
 """Tint never resolves; hue uses the real opposed check and scene retry lock."""
 if not active(target,'tinfoil',2):return information
 result=deepcopy(information)
 # Core aura hue is personality/worldview; tint is brightness/mood/intentions.
 for key in ('brightness','mood','intentions'):
  if key in result:result[key]=None
 hue_keys=set(result).intersection(('color','personality','worldview'))
 if not hue_keys:return result
 key,failed=_event(target,'tinfoil_failed_reader',scope='scene',target=reader.entity_id)
 if failed:raise ValueError('failed Aura Reader cannot retry this target during the same Scene')
 if reader_skill is None or target_skill is None:
  for field in hue_keys:result[field]=None
  return result
 if S.skill_id(engine.r.skill_policy,reader_skill,required=True) not in {S.skill_id(engine.r.skill_policy,s,required=True) for s in ('직감','집중')} or S.skill_id(engine.r.skill_policy,target_skill,required=True) not in {S.skill_id(engine.r.skill_policy,s,required=True) for s in ('오컬트학','집중')}:raise ValueError('printed Aura Reader opposed skills required')
 engine._prepare_skill_roll(reader,reader_skill,fixed=reader_roll)
 engine._prepare_skill_roll(target,target_skill,fixed=target_roll)
 attack=engine.skill_roll(reader,reader_skill,fixed=reader_roll).total
 defense=engine.skill_roll(target,target_skill,fixed=target_roll).total
 if attack<=defense:
  _state(target,True)['events'].append(key)
  for field in hue_keys:result[field]=None
 return result


def care_for(engine,actor,patients,*,rest_id,payment='ap',reason):
 """Prepare rank-two Caretaker for its actual upcoming rest; no fabricated rest."""
 W.require_actors(engine,actor,*patients);G._text(rest_id,'actual Caretaker rest identity');G._text(reason,'actual care group')
 if not active(actor,'caretaker',2):raise ValueError('rank-two Caretaker Drain during Extended Rest required')
 if type(patients)is not list or not patients or len({p.entity_id for p in patients})!=len(patients) or any(p.dead or p.kind not in ('trainer','pokemon') for p in patients):raise ValueError('actual living Trainers and Pokemon in care required')
 if payment not in ('ap','study'):raise ValueError('native post-rest Book payment required')
 if payment=='study':__import__('researcher_fields').study_points(engine,actor)
 if any(r.get('event')=='caretaker' and r['rest_id']==rest_id for r in _state(actor)['events']):raise ValueError('one actual Caretaker declaration per reader and rest identity')
 def apply(e,t,*ps):
  row={'event':'caretaker','id':'caretaker:'+t.entity_id+':'+str(len(_state(t)['events'])+1),'rest_id':rest_id,'patient_ids':[p.entity_id for p in ps],
   'provider':provider(t,'caretaker',2),'source_epoch':epoch(t),'at':e.elapsed_seconds,'payment':payment,'paid_after_rest':False,'reason':reason,'intervals':[]}
  _seal_care(row)
  _state(t,True)['events'].append(row);return deepcopy(row)
 return G.transition(engine,actor,apply,participants=patients)


def _seal_care(row):row['integrity']=_hash({k:v for k,v in row.items() if k!='integrity'})


def _care_record(engine,owner,row):
 if row.get('integrity')!=_hash({k:v for k,v in row.items() if k!='integrity'}):raise ValueError('Caretaker original changed')
 if verify_provider(engine,row['provider'],'caretaker',2) is not owner:raise ValueError('actual Caretaker reader required')
 if row['provider']['study'].get('during_rest') is not True:raise ValueError('actual rest-only Caretaker rank required')
 if type(row['patient_ids'])is not list or not row['patient_ids'] or len(set(row['patient_ids']))!=len(row['patient_ids']):raise ValueError('distinct actual Caretaker patients required')
 if type(row['paid_after_rest'])is not bool or type(row['intervals'])is not list:raise ValueError('actual Caretaker payment and intervals required')
 for interval in row['intervals']:
  if interval['reader_rest']['id']!=row['rest_id'] or owner.entity_id not in interval['actor_ids'] or not interval['start']<interval['end']<=engine.elapsed_seconds:raise ValueError('actual Caretaker reader rest interval required')
 if row['paid_after_rest']:
  rest=row['paid_rest'];parent='rest:'+_hash({'owner':owner.entity_id,'interval':rest})
  receipt=__import__('recovery_receipts').validate(owner).get(row['recovery_id'])
  if receipt is None or receipt['intent']['parent_request']!=parent or receipt['intent']['policy']!='qualified_extended_rest' or receipt['intent']['source']!='gameplay/action-points' or receipt['intent']['resource']!='ap_removed' or not receipt['eligibility']['eligible']:raise ValueError('Caretaker lost the actual qualified rest original')
 return row


@contextmanager
def rest_scope(engine,plans,minutes,rest_id):
 """Only downtime's admitted, positive native plans open this private scope."""
 if hasattr(engine,'_study_book_rest_scope'):raise ValueError('one actual shared rest scope at a time')
 actual={c.entity_id:(c,record) for c,record,*_ in plans};owners={}
 if minutes>0 and rest_id is not None:
  milestone=engine.r.mech('combat/resting')['extended_rest']['min_hours']*60
  for uid,(owner,record) in actual.items():
   if record['id']!=rest_id or record['total_minutes']<milestone:continue
   for row in _state(owner)['events']:
    if row.get('event')!='caretaker' or row['rest_id']!=rest_id:continue
    _care_record(engine,owner,row)
    if row['provider']['study']['source_id'] in _state(owner)['withdrawn']:continue
    if row['paid_after_rest']:
     usable=row['paid_epoch']==epoch(owner) and owner.spec.get('rest_interval',{}).get('id')==rest_id
    else:
     usable=row['source_epoch']==epoch(owner) and any(r['source_id']==row['provider']['study']['source_id'] for r in rows(owner,'caretaker',2))
    if usable:owners[uid]=row['id']
 start=engine.elapsed_seconds
 scope={'start':start,'end':start+minutes*60,'rest_id':rest_id,'actors':list(actual),'owners':owners,
  'id':'book-rest:'+_hash({'start':start,'end':start+minutes*60,'rest_id':rest_id,'actors':sorted(actual)})}
 engine._study_book_rest_scope=scope
 try:
  yield
  # The actual rest producer, not an outside AP/medical action, finalizes care.
  for uid,sid in owners.items():
   owner=actual[uid][0];row=next(r for r in _state(owner)['events'] if r.get('id')==sid)
   if not row['paid_after_rest']:raise ValueError('actual Caretaker Extended Rest must complete its post-rest Drain')
   interval={'id':scope['id'],'start':start,'end':engine.elapsed_seconds,'actor_ids':sorted(actual),'reader_rest':deepcopy(owner.spec['rest_interval'])}
   row['intervals'].append(interval);_seal_care(row)
  for uid,(patient,_) in actual.items():
   if care_owner(engine,patient):
    __import__('injury_recovery').recover_naturally(engine,patient)
    patient.spec['rest_interval']['context']['injuries']=patient.injuries
 finally:vars(engine).pop('_study_book_rest_scope',None)


def care_owner(engine,target,rest_id=None):
 scope=getattr(engine,'_study_book_rest_scope',None)
 if scope is None or scope['end']<=scope['start'] or not scope['start']<=engine.elapsed_seconds<=scope['end'] or target.entity_id not in scope['actors']:return None
 if rest_id is not None and rest_id!=scope['rest_id']:return None
 for uid,sid in scope['owners'].items():
  owner=W.actor_index(engine)[uid];row=next(r for r in _state(owner)['events'] if r.get('id')==sid)
  _care_record(engine,owner,row)
  if target.entity_id in row['patient_ids']:return owner,row
 return None


def care_healing(engine,target,rest_id,healing):
 return healing*2 if care_owner(engine,target,rest_id) else healing


def care_injury_bonus(engine,target):return int(care_owner(engine,target) is not None)


def after_extended_rest(engine,actor):
 scope=getattr(engine,'_study_book_rest_scope',None)
 if scope is None or actor.entity_id not in scope['owners']:return
 for row in _state(actor)['events']:
  if row.get('id')!=scope['owners'][actor.entity_id] or row['paid_after_rest']:continue
  _care_record(engine,actor,row)
  if row['source_epoch']==epoch(actor):raise ValueError('Caretaker requires actual post-rest AP recovery')
  if actor.spec.get('rest_interval',{}).get('id')!=row['rest_id']:continue
  rest=deepcopy(actor.spec['rest_interval']);parent='rest:'+_hash({'owner':actor.entity_id,'interval':rest})
  receipts=__import__('recovery_receipts').validate(actor)
  actual=[uid for uid,r in receipts.items() if r['intent']['parent_request']==parent and r['intent']['policy']=='qualified_extended_rest' and r['intent']['source']=='gameplay/action-points' and r['intent']['resource']=='ap_removed' and r['eligibility']['eligible']]
  if len(actual)!=1:raise ValueError('one actual matching Extended Rest recovery required')
  sid='caretaker-next-day:'+actor.entity_id+':'+row['rest_id']
  if row['payment']=='ap':__import__('action_points').charge(actor,1,mode='drain')
  else:__import__('researcher_fields')._drain_study(engine,actor,sid)
  row.update(paid_after_rest=True,paid_epoch=epoch(actor),paid_rest=rest,recovery_id=actual[0]);_seal_care(row)


def care_acceleration(engine,target,seconds,*,synthetic):
 found=care_owner(engine,target)
 if found is None:return 0
 owner,row=found;scope=engine._study_book_rest_scope
 from source_context import verified_source
 verified_source(engine.r,{'file':'source-audit/ptu-core-1.05.pdf','sha256':CORE_SHA},label='additive recovery rates',source_root='source-audit')
 muscle=None
 if synthetic:
  verified_source(engine.r,{'file':'input/supp-polygon-original.pdf','sha256':POLYGON_SHA},label='Synthetic Muscle upgrade')
  import csv_item_capability_contracts as CAP,move_state as MOVES
  if not CAP.has(target,'개선된 인조 근육'):raise ValueError('actual simultaneous Synthetic Muscle contribution required')
  declaration=__import__('csv_item_contract_policy').definition(engine.r,kind='improved_synthetic_muscle')
  grants=target.spec.get(G.KEY,{})
  muscle={'actor_id':target.entity_id,'capability':'개선된 인조 근육','declaration':declaration,
   'polygon_sha256':POLYGON_SHA,'baseline':list(target.spec.get('capabilities',[])),
   'legacy':deepcopy(grants.get('legacy',{}).get('capabilities',[])),
   'sources':{uid:deepcopy(value) for uid,value in grants.get('sources',{}).items() if '개선된 인조 근육' in value.get('grants',{}).get('capabilities',[]) and MOVES.source_active(target.spec,value)}}
 body={'owner_id':owner.entity_id,'care_id':row['id'],'interval_id':scope['id'],'rest_id':scope['rest_id'],
  'start':engine.elapsed_seconds-seconds,'end':engine.elapsed_seconds,'seconds':seconds,'synthetic':muscle,'provider':deepcopy(row['provider'])}
 target.spec['injury_recovery_clock'].setdefault('study_book_acceleration',[]).append(dict(body,integrity=_hash(body)))
 return seconds


def clock_extra_bound(clock):
 """Only proven simultaneous +100% Synthetic and +100% Care can exceed 2x."""
 total=0;covered=0;previous_end=-1
 for proof in clock.get('study_book_acceleration',[]):
  if proof.get('integrity')!=_hash({k:v for k,v in proof.items() if k!='integrity'}):raise ValueError('Caretaker recovery interval changed')
  seconds=C.integer(proof['seconds'],'actual Care recovery seconds',1)
  if proof['end']-proof['start']!=seconds or proof['start']<previous_end:raise ValueError('actual nonoverlapping additive recovery interval required')
  previous_end=proof['end'];muscle=proof['synthetic']
  if muscle is not None:
   if type(muscle)is not dict or muscle.get('capability')!='개선된 인조 근육' or muscle.get('polygon_sha256')!=POLYGON_SHA or muscle.get('declaration',{}).get('kind')!='improved_synthetic_muscle':raise ValueError('actual source-bound Synthetic Muscle original required')
   values=muscle['baseline']+muscle['legacy']+[value for row in muscle['sources'].values() for value in row['grants'].get('capabilities',[])]
   if muscle['capability'] not in values:raise ValueError('Synthetic Muscle original lacks its native capability contribution')
  study=proof['provider']['study']
  if study['book']!='caretaker' or study['rank']!=2 or study.get('integrity')!=_hash({k:v for k,v in study.items() if k!='integrity'}):raise ValueError('actual Care recovery source required')
  covered+=seconds;total+=seconds if muscle is not None else 0
 if covered>clock.get('known_seconds',0):raise ValueError('Care intervals exceed actual known recovery seconds')
 return total


def validate_acceleration(engine,target,clock):
 clock_extra_bound(clock)
 for proof in clock.get('study_book_acceleration',[]):
  owner=verify_provider(engine,proof['provider'],'caretaker',2)
  row=next((r for r in _state(owner)['events'] if r.get('id')==proof['care_id']),None)
  if row is None:raise ValueError('Care recovery lost its native care original')
  _care_record(engine,owner,row)
  muscle=proof['synthetic']
  if muscle is not None:
   if muscle['actor_id']!=target.entity_id or muscle['declaration']!=__import__('csv_item_contract_policy').definition(engine.r,kind='improved_synthetic_muscle'):raise ValueError('Synthetic recovery original belongs to its actual patient and source')
  interval=next((i for i in row['intervals'] if i['id']==proof['interval_id']),None)
  if interval is None or target.entity_id not in row['patient_ids'] or owner.entity_id not in interval['actor_ids'] or target.entity_id not in interval['actor_ids'] or not interval['start']<=proof['start']<proof['end']<=interval['end']<=engine.elapsed_seconds:raise ValueError('Care recovery lost its actual shared rest interval')


def assisted_breather(engine,actor,target,*,book,accept=True,save_skill='의학',fixed=None,curse_origin=None,curse_reason=None):
 """Book-specific action and native recovery; no fake permanent Feature grant."""
 W.require_actors(engine,actor,target)
 if book not in ('caretaker','combat_medic') or not active(actor,book,1 if book=='caretaker' else 2):raise ValueError('actual printed assisted-Breather Book rank required')
 if type(accept)is not bool:raise ValueError('explicit willing assisted-Breather decision required')
 if actor is target or actor.side!=target.side or not engine.adjacent(actor,target):raise ValueError('one actual adjacent ally required')
 if not engine.encounter_active:raise ValueError('assisted Book Breather requires an active encounter')
 key,used=_event(actor,book+'_breather',scope='scene')
 if used:raise ValueError('Book assisted Breather already used this Scene')
 import breather as B,turn as TURN
 B.selected(engine.r)
 origin=B._curse(engine,target,curse_origin,curse_reason)
 if isinstance(origin,C.PendingDecision):return origin
 confused=bool({'혼란','난동'}.intersection(target.conditions))
 if save_skill not in (('의학','명령') if book=='caretaker' else ('의학',)):raise ValueError('printed assisted-Breather save skill required')
 if confused:engine._prepare_skill_roll(actor,save_skill,fixed=fixed)
 elif fixed is not None:raise ValueError('no Medicine save for a clear assisted-Breather target')
 def apply(e,t,q):
  if not TURN.spend(e,t,'standard',ITEMS[book]):raise ValueError('Book assisted Breather Standard Action unavailable')
  _state(t,True)['events'].append(key)
  if not accept:return {'completed':False,'reason':'declined'}
  if confused:
   passed,total=e.skill_check(t,save_skill,12,fixed=fixed)
   if not passed:return {'completed':False,'reason':'medicine_failed','total':total}
  if book=='combat_medic':
   import initiative_interrupts as I
   suspended=e._active_turn_actor
   declaration={'id':'book-breather:'+t.entity_id+':'+str(len(_state(t)['events'])),'actor_id':q.entity_id,
    'source':ITEMS[book],'priority':0,'mode':'reaction','payment':'next','budget':{'standard':1,'shift':1},'clock':'none'}
   trigger={'kind':'turn','actor_id':suspended.entity_id,'serial':suspended.custom_conditions['combat_turn_serial'],'round':e.round_no}
   window=I.queue(e,[declaration],trigger=trigger)
   if isinstance(window,C.PendingDecision):return window
   I.begin(e,window['window_id'],declaration['id'])
   if not TURN.spend(e,q,'full',ITEMS[book]):raise ValueError('Full-Action Interrupt Breather unavailable')
   B._recover(e,q,None if origin is None else W.actor_index(e)[origin.entity_id],no_shift_trip=True)
   I.finish(e)
   return {'completed':True,'book':book,'target_id':q.entity_id,'interrupt':window['window_id']}
  B._recover(e,q,None if origin is None else W.actor_index(e)[origin.entity_id],no_shift_trip=True)
  return {'completed':True,'book':book,'target_id':q.entity_id}
 return G.transition(engine,actor,apply,participants=(target,),include_rulings=True)


def after_sprint(engine,actor):
 if active(actor,'combat_medic'):
  _state(actor,True)['events'].append({'event':'sprint','round':engine.round_no,'turn':actor.custom_conditions.get('combat_turn_serial')})


def swift_restorative(engine,actor,target,item,**options):
 if not active(actor,'combat_medic') or not engine.adjacent(actor,target):raise ValueError('Combat Medic rank one requires an adjacent target')
 stamp={'event':'sprint','round':engine.round_no,'turn':actor.custom_conditions.get('combat_turn_serial')}
 if not any(all(row.get(k)==v for k,v in stamp.items()) for row in _state(actor)['events']):raise ValueError('actual Sprint Maneuver earlier this turn required')
 if hasattr(engine,'_study_books_restorative'):raise ValueError('one actual Combat Medic item application at a time')
 engine._study_books_restorative=(actor.entity_id,target.entity_id,engine.r.item_effects(item)[1].get('id'))
 try:return __import__('items').use_item(engine,actor,item,target,**options)
 finally:vars(engine).pop('_study_books_restorative',None)


def restorative_action(engine,actor,target,item_id):
 if getattr(engine,'_study_books_restorative',None)!=(actor.entity_id,target.entity_id,item_id):return None
 if not active(actor,'combat_medic') or not engine.adjacent(actor,target):raise ValueError('actual Combat Medic Sprint application required')
 import researcher_fields as RFS
 _,_,_,kind=RFS._medicine(engine,item_id)
 if kind!='restorative':raise ValueError('Combat Medic applies an actual Restorative Item, never X Items')
 return 'swift'


def first_aid_kit(engine,actor,target,*,fixed=None,reason):
 """Actual native kit use (AP1, Extended, roll healing and three condition cures)."""
 W.require_actors(engine,actor,target);G._text(reason,'actual First Aid Kit treatment')
 if engine.encounter_active:raise ValueError('First Aid Kit is an Extended Action')
 import item_stock as STOCK,action_points as AP
 STOCK.prepare(engine,actor,'item/응급치료키트',allow_empty=False)
 if AP.available(actor)<1:raise ValueError('First Aid Kit requires one available AP')
 bonus=first_aid_bonus(actor)
 engine._prepare_skill_roll(actor,'의학',mods=bonus,fixed=fixed)
 def apply(e,t,q):
  import turn as TURN
  if not TURN.spend(e,t,'extended','item/응급치료키트'):raise ValueError('First Aid Kit Extended Action unavailable')
  AP.spend(t,1);roll=e.skill_roll(t,'의학',mods=bonus,fixed=fixed)
  healed=e.heal(q,max(0,roll.total),source_kind='ordinary_item')
  for condition in ('화상','독','마비'):e.cure_status(q,condition)
  return {'healed':healed,'medicine_total':roll.total,'book_bonus':bonus,'tool_retained':True}
 return G.transition(engine,actor,apply,participants=(target,),include_rulings=True)


def craft_mulch(engine,actor,*,food_scrap,seconds,reason):
 """The book grants the recipe; unprinted recipe cost/time remain explicit GM facts."""
 if not active(actor,'berries',2):raise ValueError('actual How Berries rank two required')
 C.integer(food_scrap,'GM Mulch Food Scrap cost',1);C.integer(seconds,'GM Mulch crafting seconds',1);G._text(reason,'GM unprinted Mulch recipe decision')
 import crafting_recipes as R
 value={'id':'study-book:mulch','source':ITEMS['berries'],'output':{'item_id':'item/비료','key':'비료'},
  'requirements':[{'id':'reader','condition':{'kind':'skill','skill':'일반 지식','rank':1,'effective':False},'reason':'actual book reader required'}],
  'materials':[{'id':'food','options':[{'kind':'value','category':'음식','amount':food_scrap,'scrap':True,'money':False}]}],'seconds':seconds}
 def apply(e,t):return R.perform(e,t,value,inputs={'food':{'option':0,'scrap_value':food_scrap}},reason=reason)
 return G.transition(engine,actor,apply,include_rulings=True)


def breeding_parents(engine,actor,parents,egg_group):
 if not daycare(actor,egg_group):return None
 from builder import species_lookup
 result=[]
 for index,parent in enumerate(parents):
  groups=species_lookup(engine.r,parent.spec['species']).get('egg_groups',[])
  if egg_group in groups:result.append(index)
 return result


def first_inheritance_level(actor,core_level):
 spec=actor.spec if hasattr(actor,'spec') else actor
 mark=spec.get('study_book_inheritance')
 if mark is None:return core_level
 if mark.get('integrity')!=_hash({k:v for k,v in mark.items() if k!='integrity'}):raise ValueError('actual Daycare hatching provider changed')
 return 10


def daycare_hatched(engine,actor,egg,pokemon):
 from builder import species_lookup
 spec=pokemon.spec if hasattr(pokemon,'spec') else pokemon
 groups=species_lookup(engine.r,spec['species']).get('egg_groups',[])
 providers=[r for r in rows(actor,'daycare',2) if r['details']['egg_group'] in groups]
 if not providers:return
 row=providers[0];mark={'provider':{'owner_id':actor.entity_id,'study':deepcopy(row)},'egg_entity_id':egg['entity_id'],'hatched_by':actor.entity_id}
 spec['study_book_inheritance']=dict(mark,integrity=_hash(mark))


def provider(actor,book,rank=1):
 """Historical source evidence, retained by actual native product/consumption."""
 candidates=rows(actor,book,rank)
 return None if not candidates else {'owner_id':actor.entity_id,'study':deepcopy(candidates[0])}


def verify_provider(engine,value,book,rank=1):
 if type(value)is not dict or set(value)!={'owner_id','study'}:raise ValueError('actual Book provider evidence required')
 owner=W.actor_index(engine).get(value['owner_id']);row=value['study']
 if owner is None or row not in _state(owner)['studies'] or row.get('book')!=book or row.get('rank',0)<rank:raise ValueError('Book provider lost its original study receipt')
 if row.get('integrity')!=_hash({k:v for k,v in row.items() if k!='integrity'}):raise ValueError('Book provider evidence changed')
 return owner


def product_created(engine,actor,production):
 """Only the native paid crafting publish path calls this producer."""
 result=production['transformation']['result']
 if production['transformation']['operation'] not in ('craft_item','craft_gem','cook_chef_food'):return
 if not result.get('product_instance_ids'):return
 if result.get('product_policy',{} ) and result['product_policy']['mode']=='repair':return
 _,header=engine.r.item_effects(result['item_id'])
 is_ball='볼' in str(header.get('category','')) or result['item_id'] in ('item/몬스터볼','item/수퍼볼','item/하이퍼볼')
 benefit={'ball_manual':provider(actor,'ball_manual',2) if is_ball else None,
          'joy_cooking':provider(actor,'joy_cooking',2) if result['item_id'] in __import__('food_effects').DRINKS else None}
 if not any(benefit.values()):return
 for uid in result.get('product_instance_ids',[]):
  mark={'production_id':production['id'],'instance_id':uid,'maker_id':actor.entity_id,'providers':deepcopy(benefit)}
  engine._physical_objects[uid]['study_book_maker']=dict(mark,integrity=_hash(mark))


def validate_product(engine,product):
 mark=product.get('study_book_maker')
 if mark is None:return None
 if mark.get('integrity')!=_hash({k:v for k,v in mark.items() if k!='integrity'}):raise ValueError('Book maker contribution changed')
 if getattr(engine,'_physical_objects',{}).get(mark['instance_id']) is not product:raise ValueError('Book maker contribution belongs to its actual physical product')
 maker=W.actor_index(engine).get(mark['maker_id'])
 row=None if maker is None else maker.spec.get('crafting_products',{}).get(mark['production_id'])
 if row is None or mark['instance_id'] not in row['transformation']['result'].get('product_instance_ids',[]):raise ValueError('Book maker contribution lost its native paid producer')
 for book,evidence in mark['providers'].items():
  if evidence is not None and verify_provider(engine,evidence,book,2) is not maker:raise ValueError('Book maker and producer differ')
 return mark


def ball_accuracy(engine,instance_id):
 if instance_id is None:return 0
 obj=getattr(engine,'_physical_objects',{}).get(instance_id)
 if obj is None:raise ValueError('actual crafted ball identity required')
 mark=validate_product(engine,obj)
 return 2 if mark and mark['providers']['ball_manual'] else 0


def dismantle_value(engine,actor,stock,price,count):
 """75% applies only to each intact physical product made by this reader."""
 import arithmetic_policy as M
 if stock is None:return M.ratio(price*count,2)
 entries=stock.get('entries',[stock]);total=0;number=0
 for entry in entries:
  amount=entry.get('count',1);number+=amount
  obj=getattr(engine,'_physical_objects',{}).get(entry.get('instance_id'))
  mark=validate_product(engine,obj) if obj is not None else None
  origin={} if obj is None else obj.get('crafting_origin',{})
  own=bool(origin.get('maker_id')==actor.entity_id and active(actor,'diy',2))
  total+=M.ratio(price*amount*(3 if own else 1),4 if own else 2)
 if number!=count:raise ValueError('actual identified dismantling stock count differs')
 return total


def read_aura(engine,reader,target,**opposed):
 """Source-selected Aura Reader remains the sole perception producer."""
 if hasattr(engine,'_study_book_aura'):raise ValueError('one actual Aura reading at a time')
 def apply(e,a,t):
  e._study_book_aura=(a.entity_id,t.entity_id,deepcopy(opposed))
  try:return __import__('aura_state').read(e,a,t)
  finally:vars(e).pop('_study_book_aura',None)
 return G.transition(engine,reader,apply,participants=(target,),include_rulings=True)


def aura_filter(engine,reader,target,information):
 value=getattr(engine,'_study_book_aura',None)
 options=value[2] if value is not None and value[:2]==(reader.entity_id,target.entity_id) else {}
 return aura_information(engine,reader,target,information,**options)


def prepared_herbal(engine,user,target,*,repeat_food_buff=False):
 """A real applicator prepares the native herbal item; no free replacement item."""
 if type(repeat_food_buff)is not bool:raise ValueError('explicit repeated Herbal Food Buff choice required')
 if repeat_food_buff and not active(user,'traditional_medicine',2):raise ValueError('rank-two Traditional Medicine Food Buff choice required')
 return {'provider':provider(user,'traditional_medicine',2 if repeat_food_buff else 1),'repeat_food_buff':repeat_food_buff,'target_id':target.entity_id}


def herbal_provider(engine,target):
 value=getattr(engine,'_study_book_herbal',None)
 if value is None or value['target_id']!=target.entity_id:return None
 evidence=value['provider']
 if evidence is None:return None
 user=verify_provider(engine,evidence,'traditional_medicine')
 if not active(user,'traditional_medicine'):raise ValueError('Herbal applicator Book benefit expired')
 return value


def use_herbal(engine,user,target,item,*,repeat_food_buff=False,**options):
 W.require_actors(engine,user,target)
 if hasattr(engine,'_study_book_herbal'):raise ValueError('one actual Herbal application at a time')
 from food_effects import HERBS
 uid=engine.r.item_effects(item)[1].get('id')
 if uid not in HERBS:raise ValueError('actual Herbal Restorative required')
 prepared=prepared_herbal(engine,user,target,repeat_food_buff=repeat_food_buff)
 engine._study_book_herbal=prepared
 try:return __import__('items').use_item(engine,user,item,target,**options)
 finally:vars(engine).pop('_study_book_herbal',None)


def validate_herbal_provider(engine,use):
 evidence=use.get('study_book')
 if evidence is None:return False
 verify_provider(engine,evidence,'traditional_medicine');return True


def herbal_protected(use):
 value=use.get('study_book')
 if value is None:return False
 row=value.get('study',{})
 if row.get('book')!='traditional_medicine' or row.get('integrity')!=_hash({k:v for k,v in row.items() if k!='integrity'}):raise ValueError('actual prepared Herbal Book source required')
 if use.get('repeat_food_buff') and row['rank']<2:raise ValueError('repeated Herbal buff requires rank two')
 return True


def identify_mushroom(engine,actor,obj):
 """Shares the one original hidden mushroom result; does not invent a DC20 roll."""
 if not active(actor,'fungi'):return None
 import herb_mushroom_rules as M
 plan=M._ensure_plan(engine,obj)
 body={'instance_id':obj['id'],'appraiser_id':actor.entity_id,'provider':provider(actor,'fungi'),'at':engine.elapsed_seconds}
 obj.setdefault('study_book_identifications',[]).append(dict(body,integrity=_hash(body)))
 return {'status':'identified','instance_id':obj['id'],'stats':list(plan['stats']),'provider':deepcopy(body['provider'])}


def fungi_recipe(engine,actor,value,ingredient,*,use):
 if type(use)is not bool:raise ValueError('explicit Fungi-only Hearty Meal provider choice required')
 if not use:return value
 if not active(actor,'fungi',2) or ingredient['item'] not in __import__('herb_mushroom_rules').MUSHROOMS:raise ValueError('rank-two Fungi Hearty Meal accepts only real mushrooms')
 value=deepcopy(value);value['source']=ITEMS['fungi']
 value['requirements']=[r for r in value['requirements'] if r['id']=='tool']
 return value


def chef_batch_created(engine,actor,batch):
 if batch['kind']!='hearty_meal':return
 evidence=provider(actor,'joy_cooking',2)
 if evidence is None:return
 body={'batch_id':batch['id'],'maker_id':actor.entity_id,'provider':evidence}
 batch['study_book_joy']=dict(body,integrity=_hash(body))


def joy_consumed(engine,user,target,plan):
 batch=plan.get('chef_batch');mark=None
 if batch is not None and plan['kind']=='hearty_meal':
  cook=W.actor_index(engine).get(batch['cook_id'])
  actual=None if cook is None else cook.spec.get('chef_batches',{}).get(batch['batch_id'])
  if actual is not None:
   mark=actual.get('study_book_joy')
   if mark is not None:
    if mark.get('integrity')!=_hash({k:v for k,v in mark.items() if k!='integrity'}) or mark['batch_id']!=actual['id'] or mark['maker_id']!=cook.entity_id:raise ValueError('actual maker meal Book contribution changed')
    verify_provider(engine,mark['provider'],'joy_cooking',2)
    production=cook.spec.get('crafting_products',{}).get(actual.get('production_id'))
    if production is None or production['transformation']['result'].get('batch_id')!=actual['id']:raise ValueError('Joy meal lost its actual paid crafting production')
 if plan['kind']=='drink':
  stock=plan['stock'];entries=stock.get('entries',[stock])
  for entry in entries:
   obj=getattr(engine,'_physical_objects',{}).get(entry.get('instance_id'))
   body=validate_product(engine,obj) if obj is not None else None
   if body and body['providers'].get('joy_cooking'):mark=body
 if not mark:return 0
 return engine.heal(target,engine.tick(target),source_kind='ordinary_item')


def harvest_record(actor,receipt):
 value=receipt.get('study_book')
 if value is None:return 0
 row=value.get('study',{})
 if value.get('owner_id')!=actor.entity_id or row not in _state(actor)['studies'] or row.get('book')!='berries' or row.get('integrity')!=_hash({k:v for k,v in row.items() if k!='integrity'}):raise ValueError('harvest bonus lost its actual Book provider')
 if not any(x.get('event')=='berries_yield' and x.get('period')==receipt['day'] and x.get('production_id')==receipt['production_id'] for x in _state(actor)['events']):raise ValueError('harvest bonus lost its actual once-daily use')
 return 1


def breeding_candidates(engine,actor,parents):
 from builder import species_lookup
 groups={r['details']['egg_group'] for r in rows(actor,'daycare')}
 return [i for i,p in enumerate(parents) if groups.intersection(species_lookup(engine.r,p.spec['species']).get('egg_groups',[]))]


def validate_world(engine,index):
 """Restore checks the same originals consumed at runtime, never a second ledger."""
 for actor in index.values():
  state=_state(actor);ids=[]
  for row in state['studies']:
   C.integer(row['rank'],'stored Book rank',1,2);C.integer(row['at'],'actual study completion',0,engine.elapsed_seconds)
   if row['source_id'] in ids:raise ValueError('duplicate Book study identity')
   ids.append(row['source_id'])
   if row['instance_id'] not in getattr(engine,'_physical_objects',{}):raise ValueError('study lost its actual physical Book')
   obj=engine._physical_objects[row['instance_id']]
   if obj.get(OBJECT,{}).get('book')!=row['book']:raise ValueError('study text and physical Book differ')
   _details(engine.r,row['book'],row['details'])
  if len(set(state['withdrawn']))!=len(state['withdrawn']) or any(sid not in ids for sid in state['withdrawn']):raise ValueError('actual distinct withdrawn Book sources required')
  rows(actor)
  for care in state['events']:
   if care.get('event')=='caretaker':_care_record(engine,actor,care)
  validate_acceleration(engine,actor,actor.spec.get('injury_recovery_clock',{}))
  for recovery in actor.spec.get('injury_healing_history',[]):
   if 'eligibility' in recovery:validate_acceleration(engine,actor,recovery['eligibility'])
  for use in actor.spec.get('herbal_restoratives',{}).get('uses',[]):validate_herbal_provider(engine,use)
  mark=actor.spec.get('study_book_inheritance')
  if mark is not None:
   first_inheritance_level(actor,20);verify_provider(engine,mark['provider'],'daycare',2)
   egg=__import__('pokemon_entities').egg_index(engine).get(mark['egg_entity_id'])
   if egg is None or not egg[1].get('hatched') or egg[1].get('pokemon_id')!=actor.entity_id:raise ValueError('Daycare inheritance lost its actual hatched egg')
 for obj in getattr(engine,'_physical_objects',{}).values():
  if OBJECT in obj:
   value=obj[OBJECT]
   if value.get('integrity')!=_hash({k:v for k,v in value.items() if k!='integrity'}):raise ValueError('physical Book text changed')
  validate_product(engine,obj)
 return True
