"""Book Style Expert declarations and native Move/Contest producers (PTU115–117).

Temporary permission is not learning. The existing action, frequency, geometry,
completion, effect clock and environment owners continue to resolve the effect.
"""
from copy import deepcopy
import common_checks as C
import contest_features as CF
import state_grants as G

CLASS=CF.STYLE
FLOURISH=CF.FLOURISH
ENTRAINMENT='feat/스타일-엔트레인먼트'
BEAUTY='feat/유혹되는-아름다움'
ENDURANCE='feat/인내력'
STATS=CF.STATS
CORRESPONDENCE=dict(zip(STATS,('spa','atk','spe','spd','def')))
RANKED={stat:row[0] for stat,row in CF.RANKED.items()}
IMPROVE={stat:row[2][0] for stat,row in CF.RANKED.items()}
SPANS={CLASS:(1179,1181),FLOURISH:(1183,1189),ENTRAINMENT:(1193,1204),
 'feat/아름다운-발레':(1212,1219),'feat/굉장함-최대':(1221,1226),BEAUTY:(1228,1232),
 'feat/근사한-행위':(1236,1244),'feat/근사함의-규칙':(1246,1251),CF.STUNT:(1253,1264),
 'feat/귀여운-포옹':(1266,1274),'feat/신나는-발걸음':(1276,1281),CF.FRIENDS:(1283,1287),
 'feat/슬기로운-계획':(1291,1299),'feat/계산된-공격':(1301,1306),CF.MISTAKES:(1308,1312),
 'feat/강인한-텀블링':(1316,1324),'feat/마초-돌진':(1326,1331),ENDURANCE:(1333,1337)}
MOVES={
 '아름다움':(('move/유혹','move/흰안개'),('move/악마의키스','move/검은눈빛')),
 '근사함':(('move/기충전','move/부르짖기'),('move/울부짖기','move/그림자분신')),
 '귀여움':(('move/애교부리기','move/블록'),('move/흔들흔들댄스','move/헤롱헤롱')),
 '슬기로움':(('move/거짓울음','move/명상'),('move/도발','move/부추기기')),
 '강인함':(('move/겁나는얼굴','move/원한'),('move/뱀눈초리','move/참기'))}
DEFINITIONS={CLASS:{'action':'static','branches':STATS},FLOURISH:{'action':'free','ap':1,'prior_features':3},
 ENTRAINMENT:{'action':'swift','ap':1,'prior_features':4,'priority':'limited'}}
for stat,(ranked,skill,children) in CF.RANKED.items():
 DEFINITIONS[ranked]={'action':'standard','ap':1,'ranks':2,'skill':skill,'branch':stat,'moves':MOVES[stat]}
 for uid in children:DEFINITIONS[uid]={'action':'free','parent':ranked,'branch':stat}
FEATURES=SPANS
CATALOG_SPANS={CLASS:(1167,1167),FLOURISH:(1183,1191),ENTRAINMENT:(1193,1208),
 RANKED['아름다움']:(1212,1217),RANKED['근사함']:(1236,1241),RANKED['귀여움']:(1266,1271),
 RANKED['슬기로움']:(1291,1296),RANKED['강인함']:(1316,1321)}


def records(actor,feature=None,active=False):
 import trainer_feature_acquisition as T
 return [row['static_acquisition'] for _,row,live in T._static_records(actor)
  if row['static_acquisition']['feature_id'] in FEATURES and (feature is None or row['static_acquisition']['feature_id']==feature)
  and (not active or live)]


def acquired(actor,feature,branch=None):
 rows=records(actor,feature,True)
 if branch is not None:rows=[row for row in rows if row['snapshot'].get('branch')==branch]
 return max(rows,key=lambda row:row['snapshot'].get('rank_number',1)) if rows else None


def acquisition_snapshot(engine,actor,feature,branch,rank_number=None):
 import acquired_features as A,skill_modifiers as S,world_entities as W
 definition=DEFINITIONS[feature]
 if feature in (CLASS,FLOURISH,ENTRAINMENT):
  if branch not in STATS:raise ValueError('exact Style Expert acquired branch required')
 elif branch is not None:raise ValueError('non-Branch Style feature does not acquire a branch')
 stat=branch if branch is not None else definition['branch']
 parent=definition.get('parent',CLASS)
 parents=[] if feature==CLASS else [row['request_id'] for row in records(actor,parent,True) if row['snapshot'].get('branch',stat)==stat]
 snapshot={'branch':stat,'parents':parents,'rank_number':rank_number or 1}
 if feature==CLASS:
  roster=[p for p in W.actor_index(engine).values() if p.kind=='pokemon' and p.spec.get('trainer_id')==actor.entity_id]
  snapshot.update(pokemon=[{'id':p.entity_id,'poffins':CF.consumed_poffins(p,actor,engine=engine).count(stat)} for p in roster],
   coordinator=A.owned_rule_count(actor,'class/코디네이터')==1)
 if feature in RANKED.values():
  snapshot['skill_rank']=S.rank(engine.r,actor,definition['skill'])[2]
  snapshot['previous']=(acquired(actor,feature) or {}).get('request_id')
 if feature in (FLOURISH,ENTRAINMENT):
  # The new instance cannot satisfy its own acquisition. Previously acquired
  # Flourish/Entrainment instances remain ordinary Features for the other one.
  snapshot['features']=[(r['source_id'],r.get('branch'),r.get('rank')) for r in
   (*A.class_instances(actor),*A.feature_instances(actor,class_source=CLASS)) if r['source_id']==CLASS or r['source_id'] in FEATURES]
 return snapshot


def qualification(actor,feature,snapshot,prerequisite_source):
 import acquisition_qualification as Q
 d=DEFINITIONS[feature];stat=snapshot.get('branch');rank=snapshot.get('rank_number')
 fields={'branch','parents','rank_number'}|({'pokemon','coordinator'} if feature==CLASS else set())|({'skill_rank','previous'} if feature in RANKED.values() else set())|({'features'} if feature in (FLOURISH,ENTRAINMENT) else set())
 if prerequisite_source is not None or type(snapshot) is not dict or set(snapshot)!=fields or stat not in STATS:
  raise ValueError('exact Style acquisition observations required')
 C.integer(rank,'Style rank',1,2 if feature in RANKED.values() else 1)
 if feature==CLASS:
  roster=snapshot['pokemon'];ids=[row['id'] for row in roster]
  if len(ids)!=len(set(ids)):raise ValueError('distinct owned Pokemon required')
  count=sum(C.integer(row['poffins'],'physical Poffin dice',0)>=3 for row in roster)
  if count<3 and not(snapshot['coordinator'] and count>=1):raise ValueError('Style requires three trained Pokemon or Coordinator and one')
 else:
  parent=d.get('parent',CLASS)
  known={row['request_id'] for row in records(actor,parent) if row['snapshot']['branch']==stat}
  if not snapshot['parents'] or not set(snapshot['parents'])<=known:raise ValueError('actual matching Style prerequisite required')
 if feature in RANKED.values():
  if snapshot['skill_rank']<(3 if rank==1 else 5):raise ValueError('printed Novice/Expert Style skill rank required')
  prior=next((r for r in records(actor,feature) if r['request_id']==snapshot['previous']),None)
  if rank==2 and (prior is None or prior['snapshot']['rank_number']!=1):raise ValueError('actual first rank required')
 if feature in (FLOURISH,ENTRAINMENT) and len(snapshot['features'])<d['prior_features']:
  raise ValueError('three/four prior Style Features required')
 return Q.require(feature,'native','acquire',[Q.check('trainer','prerequisite',actor.kind=='trainer','actual trainer required')])


def require(engine,trainer,pokemon,feature,stat=None):
 import world_entities as W
 W.require_actors(engine,trainer,pokemon);CF.owner(trainer,pokemon);CF.require(engine,trainer,feature)
 if stat is not None:
  if stat not in CF.style_expert(engine,trainer):raise ValueError('matching Style branch required')
  if feature not in (CLASS,FLOURISH,ENTRAINMENT):CF.style_training(engine,trainer,stat)


def _pay(engine,trainer,feature,pokemon,*,ap=0,per_pokemon=False,branch=None):
 import action_points as AP,frequency as F
 import combat_timing as TIME
 if per_pokemon and feature in IMPROVE.values() and any(row.get('style_used')==feature for row in TIME.records(pokemon)):
  raise ValueError('Style effect already affected this Pokemon this Scene')
 if feature==FLOURISH and branch not in STATS:raise ValueError('Style Flourish requires its acquired branch')
 key=feature+(':'+branch if feature==FLOURISH else '')+(':'+pokemon.entity_id if per_pokemon else '')
 if not F.activation_allowed(trainer,key,{'kind':'scene','uses':1},engine=engine):raise ValueError('Style effect already used this Scene')
 CF.trigger_free_action(engine,trainer,feature)
 if AP.available(trainer)<ap:raise ValueError('Style requires available AP')
 if ap:AP.spend(trainer,ap)
 F.consume_activation(trainer,key,{'kind':'scene','uses':1},engine=engine)
 if per_pokemon and feature in IMPROVE.values():TIME.install(engine,pokemon,{'source':feature,'style_used':feature,'scene_end':True})


def scope(engine,pokemon,move):
 row=next((s.get('style_expert') for s in getattr(engine,'_move_activation_scopes',()) if s['actor'] is pokemon and s['move_id']==move.get('id')),None)
 if row is None:row=getattr(engine,'_style_move_scope',None)
 if row is None or row['pokemon'] is not pokemon or row['move_id']!=move.get('id'):return None
 return row


def reaction_interested(engine,pokemon):
 """Retain a real hit receipt when a learned or acquired reaction can need it."""
 if {'move/참기','move/원한'}.intersection(pokemon.moves):return True
 import world_entities as W
 trainer=W.actor_index(engine).get(pokemon.spec.get('trainer_id'))
 if trainer is None or trainer.dead or trainer.fainted or trainer.hp<=0 or not CF.owned(trainer,RANKED['강인함']):return False
 require(engine,trainer,pokemon,RANKED['강인함'],'강인함')
 return CF.poffin_dice(engine,trainer,pokemon,'강인함',CF.style_expert(engine,trainer))>=3


def range_spec(engine,pokemon,move,result):
 row=scope(engine,pokemon,move)
 if row is None or row['effect']!=IMPROVE['아름다움']:return result
 result=deepcopy(result)
 if result.get('shape') in ('burst','blast','close_blast','cone'):result['size']+=1
 elif result.get('origin')=='melee':result={'raw':'파열 1','origin':'self','shape':'burst','size':1,'parsed':True}
 elif type(result.get('origin')) is int:result.update(raw=str(result['origin'])+', 폭발 2',shape='blast',size=2,parsed=True)
 else:raise ValueError('Fabulous Max requires an actual Melee, ranged, Burst, Blast or Cone Move')
 return result


def critical(engine,pokemon,move):
 row=scope(engine,pokemon,move)
 return 3 if row and row['effect']==IMPROVE['근사함'] else 0


def accuracy(engine,pokemon,target,move):
 row=scope(engine,pokemon,move)
 result=0
 import world_entities as W,combat_timing as TIME
 if row and row['effect']==IMPROVE['슬기로움'] and row['choice']=='focus':
  import move_completion as COMPLETE
  allies=set()
  for hit in getattr(engine,COMPLETE.KEY,{}).values():
   if hit['round']!=engine.round_no or hit.get('style_encounter_epoch')!=engine._party_encounter_epoch or hit['actor'] is pokemon or hit['actor'].side!=pokemon.side:continue
   if any(recipient.entity_id in row['target_ids'] and (r:=COMPLETE.recipient_result(hit,recipient)) and r['hit'] and not r.get('cancelled') for recipient in COMPLETE.actual_recipients(hit)):
    allies.add(hit['actor'].entity_id)
  result+=len(allies)
 for effect in TIME.records(target):
  if effect.get('style_assault') and effect['turn_owner'] is not pokemon and effect['turn_owner'].side==pokemon.side:
   result+=1
 return result


def blocks_interrupt_move(engine,event):
 row=getattr(engine,'_move_completions',{}).get(event.get('completion_id'),{})
 declaration=row.get('style_expert')
 return bool(declaration and declaration['effect']==IMPROVE['근사함'])


def begin_move(engine,row):
 row['style_encounter_epoch']=engine._party_encounter_epoch
 value=scope(engine,row['actor'],row['move'])
 if value is not None:row['style_expert']=dict(value,target_ids=[target.entity_id for target in row['targets']])


def after_move(engine,row):
 value=row.get('style_expert')
 if not value or value.get('applied') or row['phase']!='complete':return
 import move_completion as COMPLETE,combat_timing as TIME
 pokemon=row['actor'];trainer=value['trainer'];feature=value['effect']
 if value['flourish']:
  if any(row.get('style_flourish') in (True,value['stat']) for row in TIME.records(pokemon)):raise ValueError('Style Flourish already affected this target this Scene')
  engine.change_stage(pokemon,CORRESPONDENCE[value['stat']],1)
  TIME.install(engine,pokemon,{'source':FLOURISH,'style_flourish':value['stat'],'scene_end':True})
 if feature==IMPROVE['귀여움'] and value['destination'] is not None:
  import movement_actions as MOVE,arithmetic_policy as M
  speed=MOVE.capabilities(engine,pokemon).get(value['mode'],0)
  MOVE.follow_paid_path(engine,pokemon,value['destination'],mode=value['mode'],maximum_distance=M.ratio(speed,2))
 elif feature==IMPROVE['강인함']:
  import forced_movement as FORCED
  for target in COMPLETE.actual_recipients(row):
   hit=COMPLETE.recipient_result(row,target)
   if hit and hit['hit'] and not hit.get('cancelled'):
    dx=(target.pos[0]>pokemon.pos[0])-(target.pos[0]<pokemon.pos[0]);dy=(target.pos[1]>pokemon.pos[1])-(target.pos[1]<pokemon.pos[1])
    if (dx or dy) and not __import__('type_ace').push_immunity(engine,target):FORCED.displace(engine,pokemon,target,direction=(dx,dy),distance=3,source=feature,allow_fainted=True)
 elif feature==IMPROVE['슬기로움'] and value['choice']=='allies':
  for target in row['targets']:
   TIME.install(engine,target,{'source':feature,'style_assault':True,'turn_owner':pokemon,
    'turn_deadline':pokemon.custom_conditions.get('combat_turn_serial',0)+1,'encounter_end':True})
 if value.get('permission') in pokemon.spec.get(G.KEY,{}).get('sources',{}):G.revoke(pokemon,value['permission'],engine=engine)
 value['applied']=True


def use_move(engine,trainer,pokemon,target,move,*,ranked=None,effect=None,flourish=False,choice=None,destination=None,mode='land',aim=None,set_damage=False):
 """Actual public extension: one selected native Move, with its original costs."""
 import weapon_actions as W,action_points as AP,world_entities as WORLD
 WORLD.require_actors(engine,trainer,pokemon,target)
 mid=engine.r.move_id(move);native=engine.r.move(mid);stat=native.get('contest','').partition(' - ')[0].strip()
 if type(flourish) is not bool:raise ValueError('explicit Flourish boolean required')
 if ranked is None and effect is None and not flourish:raise ValueError('select a Style producer')
 if ranked is not None:
  branch=next((s for s,u in RANKED.items() if u==ranked),None)
  if branch is None:raise ValueError('exact ranked Style source required')
  require(engine,trainer,pokemon,ranked,branch)
  rank=__import__('acquired_features').feature_rank(trainer,ranked)
  if mid not in sum(MOVES[branch][:rank],()):raise ValueError('Move outside acquired Style rank')
  if CF.poffin_dice(engine,trainer,pokemon,branch,CF.style_expert(engine,trainer))<3:raise ValueError('three Poffin-derived dice required')
 if effect is not None:
  if IMPROVE.get(stat)!=effect:raise ValueError('Move contest type does not match Style effect')
  require(engine,trainer,pokemon,effect,stat)
 if flourish:
  CF.flourish(engine,trainer,pokemon,stat)
  import combat_timing as TIME
  if any(row.get('style_flourish') in (True,stat) for row in TIME.records(pokemon)):raise ValueError('Style Flourish already affected this target this Scene')
 if effect==IMPROVE['슬기로움'] and choice not in ('focus','allies'):raise ValueError('Calculated Assault chooses focus or allies')
 if effect!=IMPROVE['슬기로움'] and choice is not None:raise ValueError('unexpected Style choice')
 if effect!=IMPROVE['귀여움'] and destination is not None:raise ValueError('unexpected Style movement')
 pending=[]
 def apply(e,a,p,t):
  if hasattr(e,'_style_move_scope'):raise ValueError('nested Style Move declaration')
  value={'trainer':a,'pokemon':p,'move_id':mid,'stat':stat,'effect':effect,'flourish':flourish,
   'choice':choice,'destination':destination,'mode':mode,'target_ids':[t.entity_id],'applied':False}
  if ranked:
   if AP.available(a)<1:raise ValueError('ranked Style Move costs 1 AP')
   AP.spend(a,1)
   sid='style-permission:'+p.entity_id+':'+mid
   G.grant_moves(p,[mid],sid,'feature',owner_id=a.entity_id,lifetime='scene',rule_id=ranked,mode='permission')
   value['permission']=sid
  if effect:_pay(e,a,effect,p,per_pokemon=True)
  if flourish:_pay(e,a,FLOURISH,p,ap=1,per_pokemon=True,branch=stat)
  e._style_move_scope=value
  before=p.move_uses.get(mid,0)
  try:
   result=e.use_move_on(p,t,mid,e.everyone,aim=aim,set_damage=set_damage)
   if p.move_uses.get(mid,0)==before:raise ValueError('native Style Move activation refused')
   return result
  except Exception as error:
   import passive_events as PASSIVE,heavy_injury_adapter as HEAVY
   if type(error) is PASSIVE.PassiveEventPending and e._passive_pending==error.event_id and error.event_id in e._passive_events:
    pending.append((PASSIVE.PassiveEventPending,error.event_id));return None
   if type(error) is HEAVY.HeavyPending and e._heavy_pending==error.event_id and error.event_id in e._heavy_events:
    pending.append((HEAVY.HeavyPending,error.event_id));return None
   raise
  finally:
   del e._style_move_scope
   import conditional_damage_base as DB
   if ranked and not pending and not DB.pending_move(p,mid) and sid in p.spec.get(G.KEY,{}).get('sources',{}):G.revoke(p,sid,engine=e)
 result=G.transition(engine,trainer,apply,participants=(pokemon,target),include_rulings=True,include_grid=engine.grid is not None)
 if pending:
  exception,event=pending[0];raise exception(event)
 return result


def special_scope(engine,trainer,pokemon,mid,*,effect=None,flourish=False):
 """The same selected Tough effects, carried to a triggered Move's completion."""
 import combat_timing as TIME
 if effect is not None:
  if effect!=IMPROVE['강인함']:raise ValueError('special Tough Move needs Macho Charge')
  require(engine,trainer,pokemon,effect,'강인함')
 if flourish:
  CF.flourish(engine,trainer,pokemon,'강인함')
  if any(row.get('style_flourish') in (True,'강인함') for row in TIME.records(pokemon)):raise ValueError('Style Flourish already affected this target this Scene')
 if effect:_pay(engine,trainer,effect,pokemon,per_pokemon=True)
 if flourish:_pay(engine,trainer,FLOURISH,pokemon,ap=1,per_pokemon=True,branch='강인함')
 return {'trainer':trainer,'pokemon':pokemon,'move_id':mid,'stat':'강인함','effect':effect,'flourish':flourish,
  'choice':None,'destination':None,'mode':'land','target_ids':[],'applied':False}


def endurance_active(pokemon):
 import combat_timing as TIME
 return any(row.get('style_endurance')=='heavy' for row in TIME.records(pokemon))


def endurance(engine,trainer,pokemon,kind):
 require(engine,trainer,pokemon,ENDURANCE,'강인함')
 if kind not in ('fall','suffocation','heavy'):raise ValueError('actual Endurance trigger required')
 if kind=='heavy' and pokemon.injuries<5:raise ValueError('actual Heavy Injury trigger required')
 import arithmetic_policy as M,combat_timing as TIME
 x=M.ratio(CF.poffin_dice(engine,trainer,pokemon,'강인함',CF.style_expert(engine,trainer)),2)
 _pay(engine,trainer,ENDURANCE,pokemon)
 if kind=='heavy':TIME.install(engine,pokemon,{'source':ENDURANCE,'style_endurance':'heavy','count_deadline':(engine.round_no+x,TIME.current(engine)),'encounter_end':True})
 return x


def entice(engine,trainer,pokemon):
 require(engine,trainer,pokemon,BEAUTY,'아름다움')
 def apply(e,a,p):
  _pay(e,a,BEAUTY,p)
  sid='enticing-beauty:'+a.entity_id
  G.grant(p,'capabilities','매혹',sid,'feature',owner_id=a.entity_id,lifetime='scene',rule_id=BEAUTY)
  G._source(p,sid,'feature',enticing_beauty={'trainer_id':a.entity_id,
   'dice':CF.poffin_dice(e,a,p,'아름다움',CF.style_expert(e,a))})
  __import__('combat_timing').install(e,p,{'source':BEAUTY,'grant_source':sid,'scene_end':True})
  return sid
 return G.transition(engine,trainer,apply,participants=(pokemon,))


def lure_bonus(pokemon):
 rows=[row['enticing_beauty']['dice'] for row in pokemon.spec.get(G.KEY,{}).get('sources',{}).values() if 'enticing_beauty' in row]
 return max(rows,default=0)


def use_endurance(engine,trainer,pokemon,kind,**options):
 """Bind the actual fall/deprivation/Heavy Injury, rather than accepting a bonus."""
 import environmental_effects as ENV
 def apply(e,a,p):
  if kind=='fall':
   if options.get('meters',0)<=0:raise ValueError('actual falling damage trigger required')
   x=endurance(e,a,p,kind)
   e._style_endurance_fall=(p,x)
   try:return ENV.fall(e,p,**options)
   finally:del e._style_endurance_fall
  if kind=='suffocation':
   state=p.spec.get('_respiration')
   if options or not state or state['breathing'] or state['applied_injuries']:
    raise ValueError('actual beginning suffocation before injury required')
   x=endurance(e,a,p,kind)
   state['style_extension']=10*x
   state['grace_seconds']+=10*x
   return deepcopy(state)
  if options:raise ValueError('unexpected Endurance options')
  return endurance(e,a,p,kind)
 return G.transition(engine,trainer,apply,participants=(pokemon,),include_rulings=True)


def contest_plan(contest,c,move,ranked,effect,observed=None):
 if ranked is None and effect is None:return None
 engine,pokemon,trainer,_,_=contest._feature_binding(c)
 stat=contest.r.move_contest(move)[0]
 if ranked:
  branch=next((s for s,u in RANKED.items() if u==ranked),None)
  if branch is None:raise ValueError('exact ranked Style source required')
  require(engine,trainer,pokemon,ranked,branch)
  rank=__import__('acquired_features').feature_rank(trainer,ranked)
  if contest.r.move(move)['id'] not in sum(MOVES[branch][:rank],()):raise ValueError('Contest Move outside acquired Style rank')
  if CF.poffin_dice(engine,trainer,pokemon,branch,CF.style_expert(engine,trainer))<3:raise ValueError('three Poffin-derived dice required')
 if effect:
  if IMPROVE.get(stat)!=effect:raise ValueError('Contest Move type does not match Style effect')
  require(engine,trainer,pokemon,effect,stat)
  key=(engine,trainer.entity_id,effect,'style_alignment')
  if key in contest._flourish_used and not (observed and observed.get('state')!='complete' and observed.get('declaration',{}).get('style_effect')==effect):
   raise ValueError('Style alignment already used this Contest')
 else:key=None
 # Core264: performances explicitly ignore normal battling frequencies.
 # Native Contest consecutive-Move and feature/AP limits remain authoritative.
 return {'engine':engine,'trainer':trainer,'pokemon':pokemon,'ranked':ranked,'effect':effect,'key':key}


def contest_cost(contest,plan,other):
 if plan is None:
  if other is None:return None
  raise ValueError('native existing cost requires its binding')
 import action_points as AP
 engine,trainer=plan['engine'],plan['trainer']
 source=plan['effect'] or (other[1] if other else None)
 amount=(1 if plan['ranked'] else 0)+(other[0] if other else 0)
 if source is not None:return contest._stage_feature_cost(engine,trainer,amount,source)
 actor=deepcopy(trainer,{id(trainer.r):trainer.r})
 if AP.available(actor)<amount:raise ValueError('ranked Contest Move costs 1 AP')
 AP.spend(actor,amount)
 return actor.spec,list(getattr(trainer,'_action_history',[])),getattr(trainer,'_restricted_action_taken',False),[]
