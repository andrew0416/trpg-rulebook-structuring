"""PTK Skill Stunt: GM-approved narrow use, optional one-die replacement.
The Dowsing Rod names a different effect (+1 die); it only shares acquisition
validation and never passes its special pool through this replacement.
"""
from copy import deepcopy
import native_rule_policy as POLICY
import common_checks as C
import skill_modifiers as S
import contest_features as F
SOURCE='edge/고난이도-스킬'
ALIASES=(SOURCE,'고난이도 스킬','Skill Stunt')

def _text(value,label):
 if not isinstance(value,str) or not value.strip():raise ValueError('nonempty '+label+' required')
 return value

def count(actor):
 values=actor.spec.get('edges',[])
 if not isinstance(values,(list,tuple)):raise ValueError('actual acquired edges required')
 return sum(S.key(x) in {S.key(a) for a in ALIASES} for x in values)

def choices(e,actor,*,allow_incomplete=False):
 acquired=count(actor);mapping=actor.spec.get('edge_choices',{})
 if not isinstance(mapping,dict):raise ValueError('actual edge choices must be a mapping')
 found=[value for key,value in mapping.items() if S.key(key) in {S.key(a) for a in ALIASES}]
 if len(found)>1:raise ValueError('duplicate aliases for Skill Stunt choices')
 records=[] if not found else found[0]
 if not isinstance(records,list):raise ValueError('Skill Stunt choices must be a list')
 if not acquired:
  if records:raise ValueError('Skill Stunt choice requires an acquired edge')
  return tuple(__import__('study_books').stunts(e,actor))
 F.conscious_trainer(actor)
 if e.r._selected_rule(SOURCE)!=SOURCE:raise ValueError('selected Skill Stunt needs its own source policy')
 if (len(records)!=acquired and not allow_incomplete) or len(records)>acquired:raise ValueError('one actual narrow use per acquired Skill Stunt required')
 normalized=[]
 for index,r in enumerate(records):
  if not isinstance(r,dict) or r.get('gm_approved') is not True:raise ValueError('actual GM approval for narrow Skill Stunt use required')
  skill=r.get('skill');identity=S.skill_id(e.r.skill_policy,skill,required=True)
  if S.rank(e.r,actor,skill)[2]<3:raise ValueError('Skill Stunt chosen skill must be at least Novice')
  use=_text(r.get('use'),'approved narrow Skill Stunt use');choice_id=r.get('id','legacy:'+str(index))
  _text(choice_id,'Skill Stunt choice identity')
  normalized.append({'id':choice_id,'skill':skill,'skill_id':identity,'use':use,'gm_approved':True,'approval_reason':r.get('approval_reason'),'source':SOURCE})
 if len({r['id'] for r in normalized})!=len(normalized):raise ValueError('Skill Stunt acquisitions need distinct choice identities')
 return tuple(normalized+__import__('study_books').stunts(e,actor))

def approve(e,actor,*,choice_id,skill,use,reason,approved):
 """Bind one already acquired edge to the GM's explicit approval or refusal."""
 _text(choice_id,'choice identity');_text(use,'narrow use');_text(reason,'GM approval reason')
 if type(approved) is not bool:raise ValueError('GM approval must be explicit boolean')
 before=choices(e,actor,allow_incomplete=True)
 if not count(actor):raise ValueError('an actual acquired Skill Stunt is required')
 if len(before)>=count(actor) or choice_id in {r['id'] for r in before}:raise ValueError('no unassigned acquired Skill Stunt remains')
 identity=S.skill_id(e.r.skill_policy,skill,required=True)
 if S.rank(e.r,actor,skill)[2]<3:raise ValueError('chosen Skill Stunt skill must be Novice')
 if not approved:
  return {'source':SOURCE,'status':'gm_rejected','choice_id':choice_id,'skill':skill,'use':use,'reason':reason}
 mapping=actor.spec.setdefault('edge_choices',{})
 existing=next((k for k in mapping if S.key(k) in {S.key(a) for a in ALIASES}),SOURCE)
 mapping.setdefault(existing,[]).append({'id':choice_id,'skill':skill,'use':use,'gm_approved':True,'approval_reason':reason})
 return deepcopy(mapping[existing][-1])

def apply(e,actor,skill,resolved,declaration):
 if declaration is None:return
 if not isinstance(declaration,dict) or set(declaration)!={'choice_id','apply','matches_approved_use','reason'}:raise ValueError('Skill Stunt needs selected choice, optional application, actual matching situation and GM reason')
 if type(declaration['apply']) is not bool or type(declaration['matches_approved_use']) is not bool:raise ValueError('Skill Stunt choices must be explicit booleans')
 _text(declaration['reason'],'GM actual stunt situation reason')
 records=choices(e,actor)
 matches=[r for r in records if r['id']==declaration['choice_id']]
 if len(matches)!=1:raise ValueError('actual acquired and approved Skill Stunt choice required')
 chosen=matches[0]
 if chosen['skill_id']!=S.skill_id(e.r.skill_policy,skill,required=True):raise ValueError('Skill Stunt belongs to a different skill')
 if declaration['apply']:
  if declaration['matches_approved_use'] is not True:raise ValueError('actual situation must match the approved narrow use')
  if resolved['dice_count']<1:raise ValueError('no actual d6 available to replace')
  policy=POLICY.evaluate(e.r,'skill_stunt',{'dowsing':False})
  resolved['dice_count']+=policy['values']['pool']['dice'];resolved['modifier']+=policy['values']['pool']['modifier']
  resolved['sources']+=((SOURCE,6,chosen['use']+'; one fewer d6'),)
  resolved['skill_stunt']={'choice':deepcopy(chosen),'declaration':deepcopy(declaration)}

def for_dowsing(e,actor):
 """Dowsing's explicit item exception is +1 pool die, never this module's +6."""
 records=choices(e,actor)
 matches=[r for r in records if r['use'] in ('다우징','Dowsing','dowsing')]
 if not matches:return False
 if any(r['skill_id']!=S.skill_id(e.r.skill_policy,'오컬트학',required=True) for r in matches):raise ValueError('one approved Occult Dowsing stunt required')
 policy=POLICY.evaluate(e.r,'skill_stunt',{'dowsing':True})
 return policy['values']['pool']['dice']==1 and policy['values']['pool']['modifier']==0
