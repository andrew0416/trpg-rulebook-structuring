"""Campaign authority for Pokemon social/education skills (ch11:246-257).

Discussion records describe the chosen fiction; they do not mechanically grant
speech, obedience, capture willingness or skill ranks. The campaign decision
only controls admission to explicitly assigned skills. Source-given Porygon
Technology remains available (ch05:151), independently of the default setting.
"""
from copy import deepcopy
import re
import skill_modifiers as S
from builder import species_lookup

SOURCE='ch11-running-the-game/포켓몬으로-가득찬-세상/포켓몬의-행동과-지능'
SKILLS='ch05-pokemon/포켓몬-관리하기/스킬'
SOCIAL=frozenset(('charm','command','guile','intimidate','intuition'))
EDUCATION=S.EDUCATION_SKILLS

def _source(e):
 for uid in (SOURCE,SKILLS):
  if e.r._selected_rule(uid)!=uid:raise ValueError('selected Pokemon intelligence source requires its own policy')

def _text(value,name):
 if not isinstance(value,str) or not value.strip():raise ValueError(name+' required')
 return value

def configure(e,actor,*,portrayal,discussed_with,social,education,reason,exceptions=None):
 import pokemon_activities as P
 P._trainer(actor);P._outside(e);_source(e)
 _text(portrayal,'campaign Pokemon portrayal');_text(reason,'GM campaign decision reason')
 if not isinstance(discussed_with,(list,tuple)) or not discussed_with or any(not isinstance(x,str) or not x.strip() for x in discussed_with):raise ValueError('actual pre-game participant discussion must be recorded')
 if len(set(discussed_with))!=len(discussed_with):raise ValueError('distinct discussion participants required')
 if type(social) is not bool or type(education) is not bool:raise ValueError('social and education choices must be explicit booleans')
 exceptions=exceptions or {}
 if not isinstance(exceptions,dict):raise ValueError('individual skill exceptions must be a mapping')
 normalized={}
 actual={x.spec.get('id'):x for x in getattr(e.gm,'everyone',[]) if x.kind=='pokemon'}
 for uid,row in exceptions.items():
  if uid not in actual or not isinstance(row,dict):raise ValueError('exception requires an actual Pokemon identity')
  _text(row.get('reason'),'individual skill exception reason')
  names=row.get('skills')
  if not isinstance(names,(list,tuple)) or not names:raise ValueError('explicit individual skill list required')
  skills=[S.skill_id(e.r.skill_policy,n,required=True) for n in names]
  if len(set(skills))!=len(skills) or not set(skills).issubset(SOCIAL|EDUCATION):raise ValueError('individual exception must name distinct social or education skills')
  normalized[uid]={'skills':skills,'reason':row['reason']}
 row={'source':SOURCE,'skill_source':SKILLS,'portrayal':portrayal,'discussed_with':list(discussed_with),'social':social,'education':education,'reason':reason,'exceptions':normalized}
 e._pokemon_intelligence_policy=row
 return deepcopy(row)

def _source_exception(e,actor,sid):
 if sid!='technology education' or not actor.spec.get('species'):return False
 species=species_lookup(e.r,actor.spec['species'])['name']
 # Explicit example in ch05:151, not a numerical heuristic applied to all species.
 return species in ('폴리곤','폴리곤2','폴리곤Z')

def eligibility(e,actor,skill):
 if actor.kind!='pokemon':return True
 sid=S.skill_id(e.r.skill_policy,skill)
 if sid not in SOCIAL|EDUCATION:return True
 _source(e)
 policy=getattr(e,'_pokemon_intelligence_policy',None)
 if policy is None:return None # No declaration is not a chosen animal/human campaign.
 if policy.get('source')!=SOURCE or policy.get('skill_source')!=SKILLS:raise ValueError('campaign intelligence policy source changed')
 if type(policy.get('social')) is not bool or type(policy.get('education')) is not bool:raise ValueError('invalid campaign intelligence policy')
 if _source_exception(e,actor,sid):return True
 individual=policy.get('exceptions',{}).get(actor.spec.get('id'),{})
 return sid in individual.get('skills',[]) or policy['social' if sid in SOCIAL else 'education']

def require_skill(e,actor,skill):
 if actor.kind!='pokemon':return
 sid=S.skill_id(e.r.skill_policy,skill)
 if sid not in SOCIAL|EDUCATION:return
 allowed=eligibility(e,actor,skill)
 if allowed is False:raise ValueError('campaign Pokemon policy does not authorize this social or education skill')
 values=[v for k,v in actor.spec.get('skills',{}).items() if S.skill_id(e.r.skill_policy,k)==sid]
 if not values:raise ValueError('actual Pokemon social or education skill pool is unassigned; no default 2d6')
 # Native skill preparation performs the ordinary alias/pool validation after this gate.

def assign(e,actor,*,target,skills,reason):
 """GM-assigned concrete pools are sheet facts, not an automatic template."""
 import pokemon_activities as P
 P._trainer(actor);P._outside(e);P._pokemon(target);_text(reason,'GM assigned skill reason')
 if getattr(e,'_pokemon_intelligence_policy',None) is None:raise ValueError('discussed campaign skill policy required before assigning additional skills')
 if not isinstance(skills,dict) or not skills:raise ValueError('explicit assigned skill pools required')
 normalized={}
 for name,value in skills.items():
  sid=S.skill_id(e.r.skill_policy,name,required=True)
  if sid not in SOCIAL|EDUCATION or sid in normalized:raise ValueError('distinct campaign social or education skills required')
  if eligibility(e,target,name) is not True:raise ValueError('campaign skill eligibility required')
  if type(value) is int:
   if not 1<=value<=6:raise ValueError('ordinary assigned rank must be one through six')
  elif not isinstance(value,str) or re.fullmatch(r'[1-6]d6(?:[+-][0-9]+)?',value) is None:raise ValueError('concrete Pokemon dice pool required')
  normalized[sid]=(name,value)
 updated=deepcopy(target.spec.get('skills',{}))
 for sid,(name,value) in normalized.items():
  for old in list(updated):
   if S.skill_id(e.r.skill_policy,old)==sid:del updated[old]
  updated[name]=value
 target.spec['skills']=updated
 target.spec.setdefault('intelligence_skill_assignments',[]).append({'source':SOURCE,'reason':reason,'skills':deepcopy(skills)})
 return deepcopy(skills)
