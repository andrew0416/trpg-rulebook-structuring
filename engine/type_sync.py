"""Ch11 permanent Pokemon type adaptation with explicit GM-owned choices.

The individual owns its adapted learnset and acquisition exceptions. Catalog
species and other individuals are never rewritten. This observes a completed
GM-adjudicated Type Sync; it does not invent a supplement activation or cost.
"""
from copy import deepcopy
from pathlib import Path
import hashlib,json
import common_checks as C
import type_state as TYPES

SOURCE='ch11-running-the-game/타입-변경/포켓몬-타입-변경'
KEY='type_sync'
DECISIONS=('learning','capabilities','abilities','level_up')
FEATURE='feat/타입-동기화'
CSV='C2CSV/input/db/feats.csv:R9:main'
BOOK='input/supp-fantasy.md:524-531'
BOOK_SHA='a51f5d6592bc1ff12b380f47398db93426b53c58c210810f5041b29eb64b2266'
CSV_SHA='4435ff1c462a211564c85d2c1c9a2ac6e7c790c7545e1ad7056d32888b2367bd'
CELL_SHA='3e0fabf72f8409bc7e0fc1dfababa4f9872159fe3cb24a3c371b4ea96a7fe897'
USES='type_sync_uses'
SKILLS=('의학','오컬트학','기술학')
DEFINITION={'clause_id':BOOK,'span':[524,531],'catalog_span':[524,531],
            'source_choices':['supplement','local_csv']}

def text(value,label):
 if not isinstance(value,str) or not value.strip():raise ValueError(label+' required')
 return value

def policy(rules):
 data=json.loads((Path(rules.root)/'data/type-sync-policy.json').read_text(encoding='utf-8'))
 if rules._selected_rule(SOURCE)!=SOURCE:raise ValueError('selected Type Sync rule required')
 for file,digest in data['source_files'].items():
  if hashlib.sha256((Path(rules.root)/file).read_bytes()).hexdigest()!=digest:raise ValueError('Type Sync source anchor changed')
 return data

def resulting_types(rules,before,chosen,mode,replace_type=None):
 TYPES.validate_types(rules,before,label='Type Sync original permanent types')
 TYPES.validate_types(rules,[chosen],label='Type Sync chosen type')
 if not 1<=len(before)<=2:raise ValueError('Type Sync requires one or two original permanent types')
 if mode=='add':
  if len(before)!=1 or chosen in before or replace_type is not None:raise ValueError('add requires a distinct second type on a monotype')
  result=before+[chosen]
 elif mode=='replace':
  if replace_type not in before or chosen==replace_type:raise ValueError('replace selects one original different type')
  result=list(dict.fromkeys(chosen if t==replace_type else t for t in before))
 elif mode=='retain_chosen':
  if len(before)!=2 or chosen not in before or replace_type is not None:raise ValueError('retain_chosen requires an existing chosen type on a dual type')
  result=[chosen]
 else:raise ValueError('explicit add, replace, or retain_chosen Type Sync mode required')
 if not 1<=len(result)<=2:raise ValueError('Type Sync final permanent type count exceeds two')
 return result

def _names(values,label):
 if not isinstance(values,list) or len(set(values))!=len(values) or any(not isinstance(x,str) or not x.strip() for x in values):raise ValueError('distinct '+label+' names required')
 return list(values)

def level_rows(rules,rows):
 if not isinstance(rows,list):raise ValueError('explicit GM-reviewed level-up list required')
 result=[];seen=set()
 for row in rows:
  if not isinstance(row,dict) or set(row)!={'level','move_id'}:raise ValueError('level-up rows require level and canonical move identity')
  level=C.integer(row['level'],'Type Sync learning level',1,100);mid=row['move_id']
  if rules.move_id(mid)!=mid:raise ValueError('selected canonical level-up move required')
  if (level,mid) in seen:raise ValueError('duplicate Type Sync level-up entry')
  seen.add((level,mid));result.append({'level':level,'move_id':mid})
 return sorted(result,key=lambda x:(x['level'],x['move_id']))

def learning_rules(rules,value):
 if not isinstance(value,dict) or set(value)!={'exceptions'} or not isinstance(value['exceptions'],dict):raise ValueError('explicit reviewed body/learning exceptions mapping required')
 result={}
 for mid,row in value['exceptions'].items():
  if rules.move_id(mid)!=mid or not isinstance(row,dict) or set(row)!={'allowed','reason'} or type(row['allowed']) is not bool:raise ValueError('selected move and explicit allowed/denied learning exception required')
  result[mid]={'allowed':row['allowed'],'reason':text(row['reason'],'GM learning exception reason')}
 return {'exceptions':result}

def validate_spec(rules,spec,*,consistent=True):
 state=spec.get(KEY)
 if state is None:return True
 p=policy(rules)
 if spec.get('kind')!='pokemon' or not isinstance(state,dict) or set(state)!={'version','history'} or state['version']!=1 or not isinstance(state['history'],list) or not state['history']:raise ValueError('invalid individual Type Sync history')
 ids=set()
 for row in state['history']:
  if not isinstance(row,dict) or row.get('source')!=SOURCE or row.get('source_files')!=p['source_files'] or row.get('actor_id')!=spec.get('id'):raise ValueError('Type Sync source or individual identity changed')
  uid=text(row.get('id'),'Type Sync application identity')
  if uid in ids:raise ValueError('Type Sync application replay')
  ids.add(uid);text(row.get('reason'),'GM Type Sync reason')
  C.integer(row.get('at'),'Type Sync observed time',0);C.integer(row.get('at_level'),'Type Sync observed level',1,100)
  if not isinstance(row.get('species_id'),str):raise ValueError('Type Sync original species identity required')
  for key in ('before','after'):
   if not isinstance(row.get(key),dict) or set(row[key])!={'types','capabilities','abilities'}:raise ValueError('complete Type Sync base-state observation required')
   TYPES.validate_types(rules,row[key]['types'])
   _names(row[key]['capabilities'],'capability');_names(row[key]['abilities'],'ability')
  if 'undo_of' in row:
   text(row.get('job_id'),'Type Sync removal job');C.integer(row.get('seconds'),'completed Type Sync removal duration',1)
   prior=state['history'][:state['history'].index(row)]
   original=next((old for old in prior if old['id']==row['undo_of']),None)
   if original is None or 'feature' not in original or original['feature']['source']['edition']!='local_csv' or any(old.get('undo_of')==row['undo_of'] for old in prior):raise ValueError('Type Sync removal needs its unique original CSV application')
   if row.get('provider_id')!=original['feature']['provider_id']:raise ValueError('only the original Type Sync provider receives a refund')
   if row['after']!=_inverse(original,row['before'],prior[prior.index(original)+1:]):raise ValueError('Type Sync removal must preserve later unrelated changes')
  elif resulting_types(rules,row['before']['types'],row.get('chosen_type'),row.get('mode'),row.get('replace_type'))!=row['after']['types']:raise ValueError('Type Sync output violates the selected conversion')
  if not isinstance(row.get('decisions'),dict) or set(row['decisions'])!=set(DECISIONS):raise ValueError('all four GM Type Sync decisions required')
  for key in DECISIONS:text(row['decisions'][key],'GM '+key+' decision')
  if level_rows(rules,row.get('level_up'))!=row['level_up'] or learning_rules(rules,row.get('learning'))!=row['learning']:raise ValueError('Type Sync learned-rule projection changed')
  if 'feature' in row:
   feature=row['feature']
   if type(feature) is not dict or set(feature)!={'source','provider_id','acquisition_request_id','seconds','quota','job_id'}:raise ValueError('complete Type Sync Feature provenance required')
   if feature['source']!=feature_source(rules,feature['source'].get('edition')):raise ValueError('Type Sync Feature source changed')
   text(feature['provider_id'],'Type Sync provider');text(feature['acquisition_request_id'],'Type Sync acquisition')
   C.integer(feature['seconds'],'completed Type Sync Extended duration',1);C.integer(feature['quota'],'Type Sync rank quota',1,5)
   text(feature['job_id'],'completed Type Sync job identity')
 if consistent:
  latest=state['history'][-1]
  if latest['species_id']!=spec.get('species'):raise ValueError('Type Synced evolution needs an explicit adapted-species review')
  for key in ('types',):
   if spec.get(key,[])!=latest['after'][key]:raise ValueError('Type Sync permanent '+key+' changed outside its reviewed transition')
 return True

def active(rules,spec):
 if KEY not in spec:return None
 validate_spec(rules,spec,consistent=False)
 rows=_effective_history(spec[KEY]['history'])
 return rows[-1] if rows else None


def _effective_history(history):
 removed={row['undo_of'] for row in history if 'undo_of' in row}
 return [row for row in history if 'undo_of' not in row and (not removed or row['id'] not in removed)]

def learning_permission(rules,spec,mid,method):
 """None preserves the ordinary species route; False is an actual GM exception."""
 row=active(rules,spec)
 if row is None or method not in ('tm','hm','tutor'):return None
 if mid in row['learning']['exceptions']:return row['learning']['exceptions'][mid]['allowed']
 adapted_types={history['chosen_type'] for history in _effective_history(spec[KEY]['history'])} & set(spec.get('types',[]))
 if rules.move(mid)['type'] not in adapted_types:return None
 if method=='tutor':
  import re
  tutor_names=dict.fromkeys(re.sub(r'\s*\(N\)','',str(value),flags=re.I)
                            for species in rules.learnsets.values() for value in species.get('tutor',[]))
  ordinary={rules.move_id(name) for name in tutor_names}
  if mid not in ordinary:return None
 return True

def level_up_rows(rules,spec):
 row=active(rules,spec)
 return None if row is None else deepcopy(row['level_up'])

def historical_evidence(rules,spec,sync_id,mid,level):
 validate_spec(rules,spec,consistent=False)
 row=next((x for x in spec.get(KEY,{}).get('history',[]) if x['id']==sync_id),None)
 if row is None:return []
 return [{'source':SOURCE,'species_id':row['species_id'],'kind':'level_up','required_level':x['level'],'type_sync_id':sync_id}
         for x in row['level_up'] if x['move_id']==mid and x['level']<=level]

def observe(engine,actor,*,application_id,chosen_type,mode,replace_type=None,
            capabilities,abilities,level_up,learning,decisions,reason):
 """Atomically observe every GM choice; never infer body or ability exceptions."""
 if actor.kind!='pokemon':raise ValueError('Type Sync changes an actual Pokemon')
 text(application_id,'Type Sync application identity');text(reason,'GM Type Sync reason')
 validate_spec(engine.r,actor.spec)
 if application_id in {x['id'] for x in actor.spec.get(KEY,{}).get('history',[])}:raise ValueError('Type Sync application already observed')
 p=policy(engine.r)
 types=resulting_types(engine.r,list(actor.spec.get('types',[])),chosen_type,mode,replace_type)
 capabilities=_names(capabilities,'capability');abilities=_names(abilities,'ability')
 if not isinstance(decisions,dict) or set(decisions)!=set(DECISIONS):raise ValueError('all four GM decisions required')
 for key in DECISIONS:text(decisions[key],'GM '+key+' decision')
 rows=level_rows(engine.r,level_up);learning=learning_rules(engine.r,learning)
 import move_state as MOVES
 import state_grants as G
 import state_fields as F
 def apply(e,c):
  MOVES.record_natural_opportunities(e.r,c.spec,reason='before Type Sync: '+reason)
  before={k:deepcopy(c.spec.get(k,[])) for k in ('types','capabilities','abilities')}
  row={'id':application_id,'source':SOURCE,'source_files':deepcopy(p['source_files']),
       'actor_id':c.entity_id,'species_id':c.spec.get('species'),'at_level':c.level,'at':e.elapsed_seconds,
       'chosen_type':chosen_type,'mode':mode,'replace_type':replace_type,'before':before,
       'after':{'types':types,'capabilities':capabilities,'abilities':abilities},
       'decisions':deepcopy(decisions),'level_up':rows,'learning':learning,'reason':reason}
  F.base_patch(c,{'types':types},source=SOURCE,reason=reason)
  G.set_baseline(c,'capabilities',capabilities);G.set_baseline(c,'abilities',abilities)
  c.spec.setdefault(KEY,{'version':1,'history':[]})['history'].append(row)
  G.reconcile(e,c)
  MOVES.record_natural_opportunities(e.r,c.spec,reason='after Type Sync: '+reason)
  MOVES.validate_actor(c);validate_spec(e.r,c.spec);F.validate_actor(c)
  e.log('    '+c.name+': permanent Type Sync '+application_id,SOURCE)
  return deepcopy(row)
 return G.transition(engine,actor,apply)


def feature_source(rules,edition):
 """The local CSV is a distinct rule; it is not an official Playtest edition."""
 import csv
 import source_context as SOURCES
 import resolution_transaction as TX
 if edition not in ('supplement','local_csv'):raise ValueError('explicit reviewed Type Sync edition required')
 if rules._selected_rule(FEATURE)!=FEATURE or any(uid in rules.ruleset.unit_versions for uid in (FEATURE,BOOK,CSV)):
  raise ValueError('selected Type Sync version needs its own adapter')
 authority={'file':'input/supp-fantasy.md','sha256':BOOK_SHA}
 SOURCES.verified_source(rules,authority,label='Type Sync supplement')
 if edition=='local_csv':
  authority={'file':'input/db/feats.csv','sha256':CSV_SHA}
  SOURCES.verified_source(rules,authority,label='Type Sync CSV')
  with (Path(rules.root)/authority['file']).open(encoding='utf-8-sig',newline='') as stream:cells=list(csv.reader(stream))[8]
  if TX.json_fingerprint(cells,sort_keys=False,compact=True,allow_nan=True)!=CELL_SHA:raise ValueError('exact Type Sync CSV row changed')
  rules.ruleset.require({'id':CSV,'source':{'file':'db/feats.csv','record_span':[9,9]}})
 return dict(authority,edition=edition,clause_id=CSV if edition=='local_csv' else BOOK)


def _selection(selection):
 if type(selection) is not dict or set(selection)!={'edition','type'}:raise ValueError('exact Type Sync edition and Elemental Connection type required')
 if selection['edition'] not in ('supplement','local_csv'):raise ValueError('reviewed Type Sync source edition required')
 return selection


def _linked_classes(engine,actor,chosen):
 import acquired_features as A
 matches=[]
 for row in A.class_instances(actor):
  uid=row['source_id']
  if ((uid=='class/타입-에이스' and row['branch']==chosen) or
      (uid=='class/파동술사' and chosen=='격투') or
      (uid in ('class/염동력자','class/텔레파시능력자','class/공간도약자') and chosen=='에스퍼')):
   matches.append(row['instance_key'])
 import class_move_grants as CLASSES
 import static_feature_state_grants as STATIC
 prefix='supp-fantasy/'+('불' if chosen=='불꽃' else chosen)+'-원소술사-'
 candidates={uid for uid in engine.r.selection.units if uid.startswith(prefix) and uid.count('/')==1}
 owned={uid for uid in candidates if CLASSES._owned(actor,uid)}
 # Swarm Lord and Druid share an existing CSV/body acquisition projection.
 # Ask that owner for its verified equivalent sources instead of duplicating it.
 for row in actor.spec.get('state_grants',{}).get('sources',{}).values():
  if row.get('source_contract')!='acquired_static_feature_state_projection':continue
  definition=STATIC.rules(engine.r)[row['clause_id']]
  equivalents={binding['owner_id'] for binding in definition.get('equivalent_sources',{}).values()}
  equivalents.add(definition.get('owner_id'))
  owned.update(candidates&equivalents)
 for uid in sorted(owned):
  if engine.r._selected_rule(uid)!=uid:raise ValueError('selected Elementalist source required')
  if engine.r.selection.units[uid].get('source',{}).get('sha256')!=BOOK_SHA:raise ValueError('reviewed Elementalist source required')
  matches.append(uid)
 return matches


def acquisition_snapshot(engine,actor,selection):
 import elemental_connection as E
 import skill_modifiers as S
 selection=_selection(selection)
 return {'selection':deepcopy(selection),'source':feature_source(engine.r,selection['edition']),
         'elemental_types':list(E.choices(engine,actor)),
         'linked_classes':_linked_classes(engine,actor,selection['type']),
         'ranks':{skill:S.rank(engine.r,actor,skill)[2] for skill in SKILLS}}


def qualification(actor,snapshot,prerequisite_source):
 import acquisition_qualification as Q
 if prerequisite_source is not None or type(snapshot) is not dict or set(snapshot)!={'selection','source','elemental_types','linked_classes','ranks'}:
  raise ValueError('exact Type Sync acquisition observations required')
 selected=_selection(snapshot['selection'])
 if snapshot['source']!=feature_source(actor.r,selected['edition']):raise ValueError('immutable Type Sync acquisition source required')
 TYPES.validate_types(actor.r,[selected['type']])
 if type(snapshot['ranks']) is not dict or set(snapshot['ranks'])!=set(SKILLS):raise ValueError('all three actual Type Sync skill ranks required')
 for rank in snapshot['ranks'].values():C.integer(rank,'Type Sync skill rank',1)
 if type(snapshot['linked_classes']) is not list or any(type(v) is not str or not v for v in snapshot['linked_classes']):raise ValueError('actual type-linked Class evidence required')
 return Q.require(FEATURE,'native','acquire',[
  Q.check('trainer','prerequisite',actor.kind=='trainer','actual trainer required'),
  Q.check('elemental','prerequisite',selected['type'] in snapshot['elemental_types'],'matching Elemental Connection required'),
  Q.check('class','prerequisite',bool(snapshot['linked_classes']),'matching Type-linked Class required'),
  Q.check('skill','prerequisite',max(snapshot['ranks'].values())>=4,'Adept Medicine, Occult, or Technology required')])


def feature_record(actor,*,active=True):
 import trainer_feature_acquisition as A
 A.validate_actor(actor)
 rows=A.static_acquisitions(actor,FEATURE,active=active)
 if len(rows)!=1:raise ValueError('one actual acquired Type Sync source required')
 return rows[0][1]


def validate_feature_actor(actor):
 import trainer_feature_acquisition as A
 rows=A.static_acquisitions(actor,FEATURE,active=True)
 names={FEATURE,'타입 동기화','Type Sync'}.intersection(actor.spec.get('feats',[]))
 if bool(names)!=bool(rows) or (names and names!={FEATURE}) or len(rows)>1:
  raise ValueError('Type Sync requires its one actual acquired source')


def quota(rules,actor,edition):
 import skill_modifiers as S
 feature_source(rules,edition)
 rank=max(S.effective_rank(rules,actor,skill) for skill in SKILLS)
 # CSV counts numeric effective ranks starting at Adept inclusively; Virtuoso
 # explicitly supplies 8, hence 5 uses. Ordinary rank 7+ remains extensible.
 return max(0,min(5 if edition=='local_csv' else 4,rank-(3 if edition=='local_csv' else 2)))


def _inverse(original,current,later):
 """Invert this application's set differences, retaining later owned changes."""
 result={}
 for field in ('types','capabilities','abilities'):
  before=original['before'][field];after=original['after'][field]
  touched=set()
  for row in later:
   touched.update(set(row['before'][field])^set(row['after'][field]))
   if field=='types' and 'undo_of' not in row:touched.add(row['chosen_type'])
  added=set(after)-set(before)-touched;removed=set(before)-set(after)-touched
  result[field]=[value for value in current[field] if value not in added]
  result[field]+=[value for value in before if value in removed and value not in result[field]]
  result[field]=[value for value in before if value in result[field]]+[value for value in result[field] if value not in before]
 if not 1<=len(result['types'])<=2:raise ValueError('overlapping later Type Sync changes require GM review before removal')
 return result


def apply_feature(engine,actor,*,target,seconds,**options):
 import state_grants as G
 import pokemon_teaching as T
 import turn as TURN
 import activity_jobs as JOBS
 C.integer(seconds,'GM-established Type Sync Extended duration',1)
 T._pokemon(engine,actor,target)
 record=feature_record(actor);selection=record['snapshot']['selection']
 src=feature_source(engine.r,selection['edition']);limit=quota(engine.r,actor,selection['edition'])
 if options.get('chosen_type')!=selection['type']:raise ValueError('Type Sync must use the acquired Elemental Connection type')
 validate_spec(engine.r,target.spec)
 if any('feature' in row for row in target.spec.get(KEY,{}).get('history',[])):raise ValueError('a Pokemon may be targeted by Type Sync only once')
 uses=actor.spec.get(USES,{})
 if sum(row['refunded_by'] is None for row in uses.values())>=limit:raise ValueError('Type Sync rank quota exhausted')
 identity=text(options.get('application_id'),'Type Sync application identity')
 if identity in uses:raise ValueError('Type Sync application identity already used')
 def apply(e,p,a):
  if not TURN.spend(e,a,'extended',FEATURE):raise ValueError('Type Sync requires Extended action permission')
  job=JOBS.run_fixed(e,a,(p,),seconds=seconds,source=FEATURE,context={'type_sync_id':identity,'source_clause_id':src['clause_id']})
  observe(e,p,**options)
  row=p.spec[KEY]['history'][-1]
  row['feature']={'source':src,'provider_id':a.entity_id,'acquisition_request_id':record['request_id'],'seconds':seconds,'quota':limit,'job_id':job['job_id']}
  a.spec.setdefault(USES,{})[identity]={'target_id':p.entity_id,'source':src,'refunded_by':None}
  validate(e)
  return deepcopy(row)
 return G.transition(engine,target,apply,participants=(actor,))


def remove_feature(engine,actor,*,target,application_id,removal_id,seconds,reason):
 import state_grants as G
 import state_fields as F
 import move_state as MOVES
 import world_entities as W
 import turn as TURN
 import activity_jobs as JOBS
 W.require_actors(engine,actor,target);C.integer(seconds,'GM-established removal Extended duration',1)
 text(removal_id,'Type Sync removal identity');text(reason,'Type Sync removal reason')
 validate(engine)
 history=target.spec.get(KEY,{}).get('history',[])
 original=next((row for row in history if row['id']==application_id),None)
 if original is None or original.get('feature',{}).get('provider_id')!=actor.entity_id:raise ValueError('original Type Sync provider and target required')
 if original['feature']['source']['edition']!='local_csv':raise ValueError('the supplement does not grant CSV removal or refund')
 feature_source(engine.r,'local_csv')
 if feature_record(actor)['snapshot']['selection']['edition']!='local_csv':raise ValueError('current CSV Type Sync acquisition required for removal')
 if any(row.get('undo_of')==application_id or row['id']==removal_id for row in history):raise ValueError('Type Sync removal cannot be replayed')
 def apply(e,p,a):
  MOVES.record_natural_opportunities(e.r,p.spec,reason='before Type Sync removal: '+reason)
  before={key:deepcopy(p.spec.get(key,[])) for key in ('types','capabilities','abilities')}
  after=_inverse(original,before,history[history.index(original)+1:])
  if not TURN.spend(e,a,'extended',FEATURE):raise ValueError('Type Sync removal requires Extended action permission')
  job=JOBS.run_fixed(e,a,(p,),seconds=seconds,source=FEATURE,context={'remove_type_sync_id':application_id,'source_clause_id':CSV})
  row={'id':removal_id,'undo_of':application_id,'provider_id':a.entity_id,'source':SOURCE,
       'source_files':deepcopy(policy(e.r)['source_files']),'actor_id':p.entity_id,'species_id':p.spec['species'],
       'at_level':p.level,'at':e.elapsed_seconds,'before':before,'after':after,
       'decisions':dict.fromkeys(DECISIONS,reason),'level_up':[],'learning':{'exceptions':{}},'reason':reason,
       'job_id':job['job_id'],'seconds':seconds}
  F.base_patch(p,{'types':after['types']},source=SOURCE,reason=reason)
  for field in ('capabilities','abilities'):G.set_baseline(p,field,after[field])
  p.spec[KEY]['history'].append(row)
  a.spec[USES][application_id]['refunded_by']=removal_id
  G.reconcile(e,p)
  MOVES.record_natural_opportunities(e.r,p.spec,reason='after Type Sync removal: '+reason)
  MOVES.validate_actor(p);F.validate_actor(p);validate(e)
  return deepcopy(row)
 return G.transition(engine,target,apply,participants=(actor,))


def validate(engine):
 import world_entities as W
 actors=W.actor_index(engine)
 for actor in actors.values():
  validate_spec(engine.r,actor.spec)
  uses=actor.spec.get(USES,{})
  if type(uses) is not dict or (uses and actor.kind!='trainer'):raise ValueError('Type Sync uses belong to an actual trainer')
  for identity,use in uses.items():
   if type(use) is not dict or set(use)!={'target_id','source','refunded_by'}:raise ValueError('complete Type Sync use reference required')
   target=actors.get(use['target_id'])
   if target is None:raise ValueError('Type Sync charged target must remain an actual world Pokemon')
   rows=target.spec.get(KEY,{}).get('history',[])
   matches=[row for row in rows if row['id']==identity and row.get('feature',{}).get('provider_id')==actor.entity_id]
   if len(matches)!=1 or matches[0]['feature']['source']!=use['source']:raise ValueError('Type Sync provider charge and target provenance differ')
   refunds=[row['id'] for row in rows if row.get('undo_of')==identity]
   if refunds!=([use['refunded_by']] if use['refunded_by'] is not None else []):raise ValueError('Type Sync refund must match its actual removal')
  for row in actor.spec.get(KEY,{}).get('history',[]):
   if 'feature' in row:
    feature=row['feature'];provider=actors.get(feature['provider_id'])
    if provider is None or provider.spec.get(USES,{}).get(row['id'],{}).get('target_id')!=actor.entity_id:raise ValueError('Type Sync application lost its original provider charge')
    context={'type_sync_id':row['id'],'source_clause_id':feature['source']['clause_id']}
   elif 'undo_of' in row:
    feature=row;provider=actors.get(row['provider_id'])
    context={'remove_type_sync_id':row['undo_of'],'source_clause_id':CSV}
   else:continue
   import activity_jobs as JOBS
   job=JOBS._row(engine,feature['job_id'])
   if (job['owner'] is not provider or job['participants']!=[actor] or job['source']!=FEATURE or
       job['status']!='complete' or job['worked_seconds']!=feature['seconds'] or job['end_seconds']!=row['at'] or
       any(job['context']['observations'].get(key)!=value for key,value in context.items())):
    raise ValueError('Type Sync effect requires its actual completed Extended job')
