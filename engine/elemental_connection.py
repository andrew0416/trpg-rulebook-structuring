"""PTK ch03:508-510: owned type choices and five actual Pokemon-target checks."""
import skill_modifiers as S
import skill_targets as TARGETS
SOURCE='edge/원소-교감'
HOMEBREW='C2CSV/input/db/edges.csv:R89:main'
MYSTIC='edge/신비한-감각'
CSV_SOURCE='C2CSV/input/db/edges.csv:R55:main'
CSV_MYSTIC='C2CSV/input/db/edges.csv:R61:main'
HB_MYSTIC='C2CSV/input/db/edges.csv:R90:main'
ELEMENTAL=(SOURCE,CSV_SOURCE,HOMEBREW)
MYSTICS=(MYSTIC,CSV_MYSTIC,HB_MYSTIC)
ALIASES={SOURCE:('원소 교감','Elemental Connection'),HOMEBREW:('원소 교감 [홈브류]',),MYSTIC:('신비한 감각','Mystic Senses'),
 CSV_SOURCE:(),CSV_MYSTIC:(),HB_MYSTIC:('신비한 감각 [홈브류]',)}
SKILLS=('매력','명령','교활','협박','직감')

def matches(name,source):return S.key(name) in {S.key(x) for x in (source,*ALIASES[source])}

def _types(e,actor,source=SOURCE):
 if source not in ELEMENTAL:raise ValueError('selected elemental policy required')
 entries=[]
 for field in ('edges','feats'):
  values=actor.spec.get(field,[])
  if not isinstance(values,(list,tuple)):raise ValueError('edge ownership must be a list')
  entries.extend(values)
 count=sum(matches(x,source) for x in entries)
 values=actor.spec.get('edge_choices',{})
 if not isinstance(values,dict):raise ValueError('edge choices must be a mapping')
 selected=[v for k,v in values.items() if matches(k,source)]
 if not count:
  if selected:raise ValueError('Elemental Connection choice requires actual acquisition')
  return ()
 if actor.kind!='trainer':raise ValueError('Elemental Connection is a trainer edge')
 if e.r._selected_rule(source)!=source:raise ValueError('selected Elemental Connection variant requires its own policy')
 if source!=SOURCE and count!=1:raise ValueError('CSV Elemental Connection permits one acquired type choice')
 if len(selected)!=1:raise ValueError('one Elemental Connection choice record required')
 types=selected[0]
 if isinstance(types,str):types=(types,)
 if not isinstance(types,(list,tuple)) or len(types)!=count:raise ValueError('one elemental type per acquired branch required')
 basic=set(e.r.mech('combat/type-chart')['attack_vs_defense'])-{'에러','None'}
 if any(not isinstance(x,str) or x not in basic for x in types):raise ValueError('canonical basic elemental type required')
 if len(set(types))!=len(types):raise ValueError('each Elemental Connection branch must select a different type')
 return tuple(types)

SOURCE_OBSERVATION='elemental_connection_source_observation'
DEFAULT_INTERPRETATION='kr_branch_each_matching_type'
INTERPRETATIONS=(DEFAULT_INTERPRETATION,'kr_branch_once_per_check','en_single_acquisition')
KR_SOURCE={'file':'input/ch03-skills-edges-feats.md','sha256':'b94e43349794836391501f9aac10009d20746bf946ea0c4b5ff3adf85e982d23'}
EN_SOURCE={'file':'source-audit/elemental-connection-core-1.05.txt','sha256':'1a0f49308711bcd08a6041f1ece81533e9e7ccc38611ca64066c9539a5e73482'}
CSV_REFERENCE={'file':'input/db/edges.csv','sha256':'7a773aa7a676b4467ec8fe0c6fc3424549c3c41b2b01aee0c4c368b1abe6c609'}
FAMILY_OBSERVATION='elemental_mystic_family_source_observation'


def _family_facts(e,actor):
 from source_context import verified_source
 import root_resolution as ROOT
 facts={}
 entries=[]
 for field in ('edges','feats'):
  values=actor.spec.get(field,[])
  if not isinstance(values,(list,tuple)):raise ValueError('edge ownership must be a list')
  entries.extend(values)
 for source in (*ELEMENTAL,*MYSTICS):
  count=sum(matches(name,source) for name in entries)
  types=_types(e,actor,source) if source in ELEMENTAL else ()
  if not count:continue
  if source in MYSTICS:
   if actor.kind!='trainer' or count!=1:raise ValueError('Mystic Senses requires one trainer acquisition')
   if e.r._selected_rule(source)!=source:raise ValueError('selected Mystic Senses variant requires its own policy')
   if S.rank(e.r,actor,'직감')[2]<3:raise ValueError('Mystic Senses requires Novice Intuition')
  reference=CSV_REFERENCE if source.startswith('C2CSV/') else KR_SOURCE
  verified_source(e.r,reference,label='actual Elemental/Mystic acquired source')
  selection=e.r.select_source_definition(source)
  facts[source]={'count':count,'types':list(types),'source':reference,
   'selected_definition':selection,'definition_sha256':ROOT.fingerprint(e.r.selection.units[source]),
   'ordinary_exclusion':source not in (HOMEBREW,HB_MYSTIC)}
 return facts


def _family_document(actor,facts):
 elemental=[source for source in ELEMENTAL if source in facts] or ['']
 mystics=[source for source in MYSTICS if source in facts] or ['']
 options={a+'|'+b:{'elemental':a or None,'mystic':b or None} for a in elemental for b in mystics}
 anchor=next(iter(facts))
 return {'schema':1,'id':'native/elemental-mystic-active-definition','variants':[{
  'rule_id':anchor,'source':facts[anchor]['source'],
  'values':{'active':{'$input':'active'},'actor_id':actor.entity_id,'actual_owned':facts,'options':options,
   'interpretation':'Root-authored family alternative definitions, one active source per acquired family; active ordinary prohibition covers the named counterpart family; HB/HB omission permits that pair; no acquisition or stacked alternative bonus.'},
  'inputs':{'active':{'type':'string','authority':'gm','decision_kind':'delegated_choice',
   'choices':list(options),'question':'Select one actually acquired active Elemental and Mystic definition. This current family interpretation does not acquire an Edge, select a type, or rewrite past ownership.'}}}]}


def family_source_choices(e,actor):
 import world_entities as W,source_policy as POLICY
 W.require_actors(e,actor)
 facts=_family_facts(e,actor)
 if not facts:raise ValueError('actual acquired Elemental or Mystic family required')
 return POLICY.resolve(e.r,_family_document(actor,facts))


def _permitted_active(active):
 a,b=active['elemental'],active['mystic']
 if a and b and (a!=HOMEBREW or b!=HB_MYSTIC):
  raise ValueError('Elemental Connection and Mystic Senses are mutually exclusive under an active ordinary definition')
 return active


def _active_families(e,actor):
 import source_policy as POLICY
 facts=_family_facts(e,actor)
 if not facts:return {'elemental':None,'mystic':None},facts
 document=_family_document(actor,facts)
 options=document['variants'][0]['values']['options']
 observation=actor.spec.get(FAMILY_OBSERVATION)
 if observation is None:
  if len(options)!=1:raise ValueError('actual owned alternative definitions require an explicit current family source selection')
  active=next(iter(options.values()))
 else:
  if type(observation)is not dict or set(observation)!={'choice','policy'}:raise ValueError('actual current family source observation required')
  choice=observation['choice']
  if type(choice)is not dict or set(choice)!={'value','reason','scope'}:raise ValueError('explicit scoped family source choice required')
  resolved=POLICY.resolve(e.r,document,decisions={'active':choice})
  if resolved['status']!='PolicyValuesReady' or resolved!=observation['policy']:raise ValueError('retained family source selection changed')
  active=options[resolved['values']['active']]
 return _permitted_active(active),facts


def observe_family_source(e,actor,choice):
 from copy import deepcopy
 import action_lifecycle as ACTION,state_grants as G,world_entities as W,source_policy as POLICY
 W.require_actors(e,actor);ACTION.ensure_resolutions_clear(e)
 if type(choice)is not dict or set(choice)!={'value','reason','scope'}:raise ValueError('explicit scoped family source choice required')
 def apply(staged,actual):
  facts=_family_facts(staged,actual)
  if not facts:raise ValueError('actual acquired Elemental or Mystic family required')
  document=_family_document(actual,facts)
  resolved=POLICY.resolve(staged.r,document,decisions={'active':choice})
  if resolved['status']!='PolicyValuesReady':raise ValueError('actual current family source selection required')
  _permitted_active(resolved['values']['options'][resolved['values']['active']])
  before=deepcopy(actual.spec.get(FAMILY_OBSERVATION))
  actual.spec[FAMILY_OBSERVATION]={'choice':deepcopy(choice),'policy':resolved}
  staged.gm._rec('원소 교감/신비한 감각 활성 출처',before,deepcopy(actual.spec[FAMILY_OBSERVATION]),choice['reason'],actual)
  return deepcopy(actual.spec[FAMILY_OBSERVATION])
 return G.transition(e,actor,apply)


def require_mystic(e,actor):
 active,_=_active_families(e,actor)
 if active['mystic'] is None:raise ValueError('Mystic Senses acquisition required')
 return active['mystic']


def _source_resolution(e,actor,types,choice=None):
 from source_context import verified_source
 import source_policy as POLICY
 verified_source(e.r,KR_SOURCE,label='Elemental Connection KR Branch')
 verified_source(e.r,EN_SOURCE,source_root='source-audit',label='Elemental Connection EN single acquisition')
 document={'schema':1,'id':'native/elemental-connection-source','variants':[{
  'rule_id':SOURCE,'source':KR_SOURCE,
  'values':{'interpretation':{'$input':'interpretation'},'actor_id':actor.entity_id,
            'acquired_types':list(types),'english_source':EN_SOURCE,
            'interpretation_kinds':{DEFAULT_INTERPRETATION:'KR Branch; authored additive overlap interpretation',
              'kr_branch_once_per_check':'KR Branch; explicit GM once-per-check overlap interpretation',
              'en_single_acquisition':'EN explicit general single-acquisition rule and untagged Edge'}},
  'inputs':{'interpretation':{'type':'string','authority':'gm','decision_kind':'source_conflict',
   'choices':list(INTERPRETATIONS),
   'question':'Choose complete native Elemental semantics: KR/EN differ on repeat acquisition; the two KR overlap readings are explicit GM interpretations, not separate printed editions.'}}}]}
 return POLICY.resolve(e.r,document,decisions={} if choice is None else {'interpretation':choice})


def _interpretation(e,actor,types):
 observation=actor.spec.get(SOURCE_OBSERVATION)
 # Root-authored default for an unselected current native rule. No historical
 # source choice or acquisition receipt is fabricated by reading the modifier.
 if observation is None:return DEFAULT_INTERPRETATION
 if type(observation)is not dict or set(observation)!={'choice','policy'}:raise ValueError('actual Elemental source observation required')
 choice=observation['choice']
 if type(choice)is not dict or set(choice)!={'value','reason','scope'}:raise ValueError('explicit scoped Elemental source choice required')
 resolved=_source_resolution(e,actor,types,choice)
 if resolved['status']!='PolicyValuesReady' or resolved!=observation['policy']:raise ValueError('retained Elemental source choice changed')
 return resolved['values']['interpretation']


def source_choices(e,actor):
 """Pure actual-owner query; a source observation never grants an Edge."""
 import world_entities as W
 W.require_actors(e,actor)
 types=_types(e,actor,SOURCE)
 if not types:raise ValueError('actual native Elemental acquisition required')
 return _source_resolution(e,actor,types)


def observe_source(e,actor,choice):
 """Record one actual current scoped GM choice through the existing state owner."""
 from copy import deepcopy
 import state_grants as G,world_entities as W
 W.require_actors(e,actor)
 if type(choice)is not dict or set(choice)!={'value','reason','scope'}:raise ValueError('explicit scoped Elemental source choice required')
 def apply(staged,actual):
  types=_types(staged,actual,SOURCE)
  if not types:raise ValueError('actual native Elemental acquisition required')
  resolved=_source_resolution(staged,actual,types,choice)
  if resolved['status']!='PolicyValuesReady':raise ValueError('current Elemental source choice required')
  if resolved['values']['interpretation']=='en_single_acquisition' and len(types)!=1:raise ValueError('English Elemental Connection permits one acquired type choice')
  before=deepcopy(actual.spec.get(SOURCE_OBSERVATION))
  actual.spec[SOURCE_OBSERVATION]={'choice':deepcopy(choice),'policy':resolved}
  staged.gm._rec('원소 교감 출처 해석',before,deepcopy(actual.spec[SOURCE_OBSERVATION]),choice['reason'],actual)
  return deepcopy(actual.spec[SOURCE_OBSERVATION])
 return G.transition(e,actor,apply)


def choices(e,actor,source=SOURCE):
 if source not in ELEMENTAL:raise ValueError('selected elemental policy required')
 active,facts=_active_families(e,actor)
 types=tuple(facts[source]['types']) if active['elemental']==source else ()
 if source==SOURCE and types:
  interpretation=_interpretation(e,actor,types)
  if interpretation=='en_single_acquisition' and len(types)!=1:raise ValueError('English Elemental Connection permits one acquired type choice')
 return types


def register_owned(e,actor,name):
 if any(matches(name,source) for source in ALIASES):
  _active_families(e,actor)
  # Both edges are consumed by native target-aware activity paths.
  return True
 return False

def modifier(e,actor,skill,target):
 TARGETS.validate(e,target)
 active,facts=_active_families(e,actor)
 source=active['elemental']
 types=choices(e,actor,source) if source else ()
 branches=[(source,types)] if types else []
 if not branches or target is None or target.kind!='pokemon':return ()
 if S.skill_id(e.r.skill_policy,skill) not in {S.skill_id(e.r.skill_policy,x) for x in SKILLS}:return ()
 actual=target.types
 if not isinstance(actual,(list,tuple)) or not actual:raise ValueError('actual Pokemon types required for Elemental Connection')
 matching=tuple((source,x) for source,types in branches for x in types if x in actual)
 if len(matching)>1:
  types=next(types for source,types in branches if source==SOURCE)
  if _interpretation(e,actor,types)=='kr_branch_once_per_check':matching=matching[:1]
 return tuple((source,2,element) for source,element in matching)
