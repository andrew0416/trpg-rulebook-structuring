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
  if resulting_types(rules,row['before']['types'],row.get('chosen_type'),row.get('mode'),row.get('replace_type'))!=row['after']['types']:raise ValueError('Type Sync output violates the selected conversion')
  if not isinstance(row.get('decisions'),dict) or set(row['decisions'])!=set(DECISIONS):raise ValueError('all four GM Type Sync decisions required')
  for key in DECISIONS:text(row['decisions'][key],'GM '+key+' decision')
  if level_rows(rules,row.get('level_up'))!=row['level_up'] or learning_rules(rules,row.get('learning'))!=row['learning']:raise ValueError('Type Sync learned-rule projection changed')
 if consistent:
  latest=state['history'][-1]
  if latest['species_id']!=spec.get('species'):raise ValueError('Type Synced evolution needs an explicit adapted-species review')
  for key in ('types',):
   if spec.get(key,[])!=latest['after'][key]:raise ValueError('Type Sync permanent '+key+' changed outside its reviewed transition')
 return True

def active(rules,spec):
 if KEY not in spec:return None
 validate_spec(rules,spec,consistent=False)
 return spec[KEY]['history'][-1]

def learning_permission(rules,spec,mid,method):
 """None preserves the ordinary species route; False is an actual GM exception."""
 row=active(rules,spec)
 if row is None or method not in ('tm','hm','tutor'):return None
 if mid in row['learning']['exceptions']:return row['learning']['exceptions'][mid]['allowed']
 adapted_types={history['chosen_type'] for history in spec[KEY]['history']} & set(spec.get('types',[]))
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
