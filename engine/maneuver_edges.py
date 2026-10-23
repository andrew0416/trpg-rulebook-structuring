"""Owned bonuses and success-only usage for specific opposed maneuvers."""
import skill_modifiers as SKILL
import common_checks as C
import composition_derive as COMPOSITION
POLICIES={
 'maneuver/술수':('edge/전문적인-조종자',('전문적인 조종자','Expert Manipulator'),'교활'),
 'maneuver/치사한-짓':('edge/전문-트릭스터',('전문 트릭스터','Expert Trickster'),'은신'),
}

def owns(e,actor,source):
 uid,aliases,skill=POLICIES[source]
 entries=[]
 for field in ('edges','feats'):
  values=actor.spec.get(field,[])
  if not isinstance(values,(list,tuple)):raise ValueError('maneuver edge ownership must be a list')
  entries.extend(values)
 names={SKILL.key(x) for x in (uid,*aliases)}
 count=sum(SKILL.key(x) in names for x in entries)
 if not count:return False
 if count!=1 or actor.kind!='trainer':raise ValueError('maneuver edge requires exactly one trainer acquisition')
 if e.r._selected_rule(uid)!=uid:raise ValueError('selected maneuver edge variant requires its own policy')
 if SKILL.rank(e.r,actor,skill)[2]<4:raise ValueError('maneuver edge prerequisite is not established')
 return True

def register_owned(e,actor,name):
 for source,(uid,aliases,skill) in POLICIES.items():
  if SKILL.key(name) in {SKILL.key(x) for x in (uid,*aliases)}:
   owns(e,actor,source)
   return True
 return False

def options(e,actor,source,supplied):
 out=dict(supplied or {})
 extra=out.get('mods',0);C.integer(extra,'maneuver modifier')
 if owns(e,actor,source):
  uid=POLICIES[source][0]
  out['mods']=COMPOSITION.derive(extra,[{'id':uid,'source':uid,'value':2}],
   [{'law':'add','contributors':[uid]}])['value']
 return out

def success_only(e,actor,target,source):
 enabled=owns(e,actor,source)
 if enabled and (getattr(actor,'side',None) is None or getattr(target,'side',None) is None):
  raise ValueError('success-only enemy usage requires established side relations')
 return enabled

def charge_on_success(actor,target,source,kind,key,succeeded):
 if succeeded and actor.side!=target.side:
  entries=actor.custom_conditions.setdefault(key,[])
  if not any(k==kind and victim is target for k,victim in entries):entries.append((kind,target))
