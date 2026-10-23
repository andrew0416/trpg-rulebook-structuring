"""PTK ch11:259-288: qualitative understanding and campaign action policies.

Domains are independent, scoped GM facts, never a universal IQ or skill bonus.
A known command does not establish loyalty; language does not grant education.
Water type never establishes aquatic anatomy or current water exposure.
"""
from copy import deepcopy
import json,hashlib
import common_checks as C

SOURCE='ch11-running-the-game/포켓몬으로-가득찬-세상/포켓몬의-행동과-지능'
DOMAINS=('basic_commands','habitat_survival','spatial_memory','tool_use','social_structure','human_language','education')
ACTIVITY_KINDS=('move','movement','skill','request')
LANGUAGE_CAPABILITIES=('텔레파시','파동감지','파동술','언어')

import resolution_transaction as _FINGERPRINTS

def source(e):
 if e.r._selected_rule(SOURCE)!=SOURCE:raise ValueError('selected understanding/campaign source requires its own policy')

def _text(value,name):
 if not isinstance(value,str) or not value.strip():raise ValueError(name+' required')
 return value

def _target(e,actor,target,*,outside=True):
 import pokemon_activities as P
 P._trainer(actor);P._pokemon(target);source(e)
 if outside:P._outside(e)
 _text(target.spec.get('id'),'actual Pokemon identity')
 for other in getattr(e.gm,'everyone',[]):
  if other is not target and other.spec.get('id')==target.spec['id']:raise ValueError('duplicate Pokemon identity')

def settings(e,actor,*,humanlike,outside_water,discussed_with,reason):
 import pokemon_activities as P
 P._trainer(actor);P._outside(e);source(e)
 if type(humanlike) is not bool:raise ValueError('explicit humanlike campaign choice required')
 if not isinstance(outside_water,dict) or set(outside_water)!=set(ACTIVITY_KINDS) or any(type(x) is not bool for x in outside_water.values()):raise ValueError('explicit outside-water eligibility for each action kind required')
 if not isinstance(discussed_with,(list,tuple)) or not discussed_with or any(not isinstance(x,str) or not x.strip() for x in discussed_with) or len(set(discussed_with))!=len(discussed_with):raise ValueError('distinct informed campaign participants required')
 _text(reason,'GM campaign setting reason')
 row={'source':SOURCE,'humanlike':humanlike,'outside_water':deepcopy(outside_water),'discussed_with':list(discussed_with),'reason':reason}
 e._pokemon_setting_policy=row
 return deepcopy(row)

def observe_body(e,actor,*,target,aquatic_body,in_water,reason):
 _target(e,actor,target,outside=False)
 if type(aquatic_body) is not bool or type(in_water) is not bool:raise ValueError('actual aquatic anatomy and current water exposure must be explicit booleans')
 _text(reason,'GM observed body/environment reason')
 row={'source':SOURCE,'pokemon_id':target.spec['id'],'aquatic_body':aquatic_body,'in_water':in_water,'reason':reason}
 target.spec['pokemon_body_environment']=row
 return deepcopy(row)

def require_activity(e,actor,activity):
 if actor.kind!='pokemon':return
 if activity not in ACTIVITY_KINDS:raise ValueError('known Pokemon activity category required')
 if actor.spec.get('regional_variant'):
  import regional_pokemon as REGIONAL
  REGIONAL.validate_actor(e,actor)
 body=actor.spec.get('pokemon_body_environment')
 if body is None:return # No aquatic anatomy is inferred from species/type prose.
 source(e)
 if body.get('source')!=SOURCE or body.get('pokemon_id')!=actor.spec.get('id'):raise ValueError('actual body/environment source identity changed')
 if type(body.get('aquatic_body')) is not bool or type(body.get('in_water')) is not bool:raise ValueError('body/environment is unresolved')
 if not body['aquatic_body'] or body['in_water']:return
 policy=getattr(e,'_pokemon_setting_policy',None)
 if policy is None:raise ValueError('campaign outside-water action policy is unresolved')
 if policy.get('source')!=SOURCE:raise ValueError('campaign outside-water source changed')
 permission=policy.get('outside_water',{}).get(activity)
 if type(permission) is not bool:raise ValueError('outside-water action permission must be explicit')
 if not permission:raise ValueError('campaign outside-water policy does not permit this aquatic Pokemon action')
 # Admission alone grants no land/levitation capability, breath, damage immunity or action.

def profile(e,actor,*,target,habitat,organization,domains,reason):
 _target(e,actor,target);_text(habitat,'actual natural habitat');_text(organization,'GM social organization description');_text(reason,'GM understanding profile reason')
 if not isinstance(domains,dict) or not set(domains).issubset(DOMAINS):raise ValueError('understanding uses separately named domains, not a scalar intelligence score')
 rows={
  'basic_commands':{'status':'expected','scope':'ordinary basic battle commands','basis':'source baseline; does not imply obedience'},
  'habitat_survival':{'status':'expected','scope':habitat,'basis':'ordinary survival in its actual natural habitat; no universal success'},
 }
 for domain,row in domains.items():
  if not isinstance(row,dict) or row.get('status') not in ('established','not_established','unknown'):raise ValueError('each domain needs its independently established status')
  _text(row.get('scope'),'domain scope');_text(row.get('basis'),'domain evidence or experience')
  rows[domain]={k:row[k] for k in ('status','scope','basis')}
 old=target.spec.get('pokemon_understanding',{})
 row={'source':SOURCE,'pokemon_id':target.spec['id'],'revision':old.get('revision',0)+1,'habitat':habitat,'organization':organization,'domains':rows,'reason':reason,'experiences':deepcopy(old.get('experiences',[]))}
 target.spec['pokemon_understanding']=row
 return deepcopy(row)

def record_experience(e,actor,*,target,event_id,domains,description):
 """Record actual observed education; no XP/TP or general score is inferred."""
 _target(e,actor,target);_text(event_id,'actual education/experience event identity');_text(description,'observed education/experience description')
 old=target.spec.get('pokemon_understanding')
 if not old or old.get('source')!=SOURCE or old.get('pokemon_id')!=target.spec.get('id'):raise ValueError('actual source-bound understanding profile required')
 if any(x['id']==event_id for x in old.get('experiences',[])):raise ValueError('experience event already recorded')
 if not isinstance(domains,dict) or not domains or not set(domains).issubset(DOMAINS):raise ValueError('explicit affected understanding domains required')
 changes={}
 for domain,row in domains.items():
  if not isinstance(row,dict) or row.get('status') not in ('established','not_established','unknown'):raise ValueError('explicit learned status required')
  _text(row.get('scope'),'learned scope');changes[domain]={'status':row['status'],'scope':row['scope'],'basis':description,'event_id':event_id}
 result=deepcopy(old);result['revision']+=1;result['domains'].update(changes)
 result.setdefault('experiences',[]).append({'id':event_id,'description':description,'domains':list(changes),'recorded_at':e.elapsed_seconds})
 target.spec['pokemon_understanding']=result
 return deepcopy(result)

def requirements(value):
 if value is None:return None
 if not isinstance(value,dict) or set(value)!=set(('domains','context')):raise ValueError('understanding request must name domains and actual task context')
 names=value['domains']
 if not isinstance(names,(list,tuple)) or not names or len(set(names))!=len(names) or not set(names).issubset(DOMAINS):raise ValueError('distinct understanding domains required')
 _text(value['context'],'actual task understanding context')
 return {'domains':list(names),'context':value['context']}

def _basis(e,target,request):
 profile=target.spec.get('pokemon_understanding')
 if not profile or profile.get('source')!=SOURCE or profile.get('pokemon_id')!=target.spec.get('id'):raise ValueError('actual Pokemon understanding profile required for this scoped request')
 data={'source':SOURCE,'pokemon_id':target.spec['id'],'profile':profile,'settings':getattr(e,'_pokemon_setting_policy',None),
       'request':{k:request.get(k) for k in ('id','trainer_id','pokemon_id','intent','action','requested_options','understanding_requirements')}}
 return _FINGERPRINTS.json_fingerprint(data, sort_keys=True, compact=False, allow_nan=False)

def _language_capability(e,target,name):
 if name not in LANGUAGE_CAPABILITIES:raise ValueError('only the explicitly named communication capabilities support this exception')
 import state_grants as GRANTS
 if name not in GRANTS.effective(target,'capabilities'):raise ValueError('actual owned communication capability required')
 uid='capability/'+name
 if uid in e.r.selection.units and e.r._selected_rule(uid)!=uid:raise ValueError('selected communication capability requires its own understanding policy')

def assess(e,actor,*,target,request_id,decisions,reason,language_exception=None):
 _target(e,actor,target)
 import pokemon_activities as P
 P._owner(actor,target);_text(reason,'GM task-specific understanding reasons')
 request=actor.spec.get('pokemon_requests',{}).get(request_id)
 if not request or request.get('trainer_id')!=actor.spec.get('id') or request.get('pokemon_id')!=target.spec['id']:raise ValueError('actual request ownership required')
 if request.get('status')!='awaiting_gm':raise ValueError('cannot replace understanding behind an already observed or consumed request')
 needs=requirements(request.get('understanding_requirements'))
 if needs is None:raise ValueError('request has no declared understanding requirements')
 if not isinstance(decisions,dict) or set(decisions)!=set(needs['domains']) or any(v is not None and type(v) is not bool for v in decisions.values()):raise ValueError('each requested domain needs an independent true/false/unknown decision')
 if language_exception is not None:
  _language_capability(e,target,language_exception)
  if 'human_language' not in decisions or decisions['human_language'] is not True:raise ValueError('communication exception applies only to the explicitly accepted human-language facet')
 row={'source':SOURCE,'basis':_basis(e,target,request),'decisions':deepcopy(decisions),'reason':reason,'language_exception':language_exception}
 request['understanding_assessment']=row
 return deepcopy(row)

def require_request(e,actor,target,request):
 require_activity(e,target,'request')
 if request.get('understanding_requirements') is None:return
 source(e);row=request.get('understanding_assessment')
 if not row or row.get('source')!=SOURCE:raise ValueError('GM task-specific understanding assessment required')
 if row.get('basis')!=_basis(e,target,request):raise ValueError('understanding source, profile or actual request changed after assessment')
 if row.get('language_exception'):_language_capability(e,target,row['language_exception'])
 needs=requirements(request['understanding_requirements'])
 if set(row.get('decisions',{}))!=set(needs['domains']) or any(v is not True for v in row['decisions'].values()):raise ValueError('one or more required understanding facets are false or unresolved')

ACTIVITIES={'pokemon_settings':settings,'observe_pokemon_body':observe_body,'understanding_profile':profile,'record_pokemon_experience':record_experience,'assess_pokemon_request':assess}

