"""PTK ch03:508-510: owned type choices and five actual Pokemon-target checks."""
import skill_modifiers as S
import skill_targets as TARGETS
SOURCE='edge/원소-교감'
HOMEBREW='C2CSV/input/db/edges.csv:R89:main'
MYSTIC='edge/신비한-감각'
ALIASES={SOURCE:('원소 교감','Elemental Connection'),HOMEBREW:('원소 교감 [홈브류]',),MYSTIC:('신비한 감각','Mystic Senses')}
SKILLS=('매력','명령','교활','협박','직감')

def matches(name,source):return S.key(name) in {S.key(x) for x in (source,*ALIASES[source])}

def choices(e,actor,source=SOURCE):
 if source not in (SOURCE,HOMEBREW):raise ValueError('selected elemental policy required')
 entries=[]
 for field in ('edges','feats'):
  values=actor.spec.get(field,[])
  if not isinstance(values,(list,tuple)):raise ValueError('edge ownership must be a list')
  entries.extend(values)
 count=sum(matches(x,source) for x in entries)
 mystic=sum(matches(x,MYSTIC) for x in entries)
 if mystic:
  if mystic!=1 or actor.kind!='trainer':raise ValueError('Mystic Senses requires one trainer acquisition')
  if e.r._selected_rule(MYSTIC)!=MYSTIC:raise ValueError('selected Mystic Senses variant requires its own policy')
  if S.rank(e.r,actor,'직감')[2]<3:raise ValueError('Mystic Senses requires Novice Intuition')
 if source==SOURCE and count and mystic:raise ValueError('Elemental Connection and Mystic Senses are mutually exclusive')
 values=actor.spec.get('edge_choices',{})
 if not isinstance(values,dict):raise ValueError('edge choices must be a mapping')
 selected=[v for k,v in values.items() if matches(k,source)]
 if not count:
  if selected:raise ValueError('Elemental Connection choice requires actual acquisition')
  return ()
 if actor.kind!='trainer':raise ValueError('Elemental Connection is a trainer edge')
 if e.r._selected_rule(source)!=source:raise ValueError('selected Elemental Connection variant requires its own policy')
 if source==HOMEBREW and count!=1:raise ValueError('homebrew Elemental Connection permits one acquired type choice')
 if len(selected)!=1:raise ValueError('one Elemental Connection choice record required')
 types=selected[0]
 if isinstance(types,str):types=(types,)
 if not isinstance(types,(list,tuple)) or len(types)!=count:raise ValueError('one elemental type per acquired branch required')
 basic=set(e.r.mech('combat/type-chart')['attack_vs_defense'])-{'에러','None'}
 if any(not isinstance(x,str) or x not in basic for x in types):raise ValueError('canonical basic elemental type required')
 if len(set(types))!=len(types):raise ValueError('each Elemental Connection branch must select a different type')
 return tuple(types)

def register_owned(e,actor,name):
 if any(matches(name,source) for source in ALIASES):
  choices(e,actor)
  choices(e,actor,HOMEBREW)
  # Both edges are consumed by native target-aware activity paths.
  return True
 return False

def modifier(e,actor,skill,target):
 TARGETS.validate(e,target)
 branches=[(source,types) for source in (SOURCE,HOMEBREW) if (types:=choices(e,actor,source))]
 if not branches or target is None or target.kind!='pokemon':return ()
 if S.skill_id(e.r.skill_policy,skill) not in {S.skill_id(e.r.skill_policy,x) for x in SKILLS}:return ()
 actual=target.types
 if not isinstance(actual,(list,tuple)) or not actual:raise ValueError('actual Pokemon types required for Elemental Connection')
 matching=tuple((source,x) for source,types in branches for x in types if x in actual)
 if len(matching)>1:raise ValueError('multiple matching elemental branches need an explicit sourced stacking policy')
 return ((matching[0][0],2,matching[0][1]),) if matching else ()
