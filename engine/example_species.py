"""Source-derived example species sharing ordinary creation/growth consumers.

Definitions are declarative deltas over stock templates, not actor mutation.
Core examples keep their source identity and do not become custom homebrew
rules merely because the Korean translation needs a recorded correction.
"""
from copy import deepcopy
from pathlib import Path
import json,hashlib
from ruleset import ExcludedRuleSelection

SOURCE='ch11-running-the-game/이로치-포켓몬/이로치-포켓몬의-예시'

import resolution_transaction as _FINGERPRINTS

def policy(rules):
 data=json.loads((Path(rules.root)/'data/example-species-policy.json').read_text(encoding='utf-8'))
 if data.get('schema_version')!=1 or data.get('source')!=SOURCE:raise ValueError('reviewed example species policy required')
 for file,digest in data['source_files'].items():
  if hashlib.sha256((Path(rules.root)/file).read_bytes()).hexdigest()!=digest:raise ValueError('example species source anchor changed: '+file)
 return data

def union(left,right):
 result=deepcopy(left)
 for row in right:
  if row not in result:result.append(deepcopy(row))
 return result

def install(rules):
 data=policy(rules)
 try:selected=rules._selected_rule(SOURCE)==SOURCE
 except (KeyError,ValueError):selected=False
 if not selected:return
 # The source supplies defender charts and a STAB alias, not Glass attacks.
 # Keep these definitions with the existing immutable example policy.
 from type_state import CORE_TYPES
 defenders=deepcopy(data.get('defender_types',{}))
 for name,row in defenders.items():
  if name in CORE_TYPES or not isinstance(name,str) or not name:raise ValueError('distinct source defender type required')
  if not set(row.get('stab_types',[]))<=set(CORE_TYPES):raise ValueError('selected core STAB identities required')
  charts=[row.get('defense_steps')]
  for combination in row.get('combinations',[]):
   values=combination.get('types',[])
   if len(values)!=len(set(values)) or name not in values or not set(values)<=(set(CORE_TYPES)|{name}):raise ValueError('explicit source defensive combination required')
   charts.append(combination.get('defense_steps'))
  for chart in charts:
   if not isinstance(chart,dict) or set(chart)!=set(CORE_TYPES) or any(v is not None and (type(v) is not int or v not in (-3,-2,-1,0,1,2,3)) for v in chart.values()):raise ValueError('complete source defensive net-step chart required')
 machines=json.loads((Path(rules.root)/'data/pokemon-machines.json').read_text(encoding='utf-8'))['machines']
 prepared=[]
 for definition in data['definitions']:
  base=rules.species[definition['base_species']]
  sp=deepcopy(base);old=base['name'];name=definition['name'];uid=definition['id']
  if uid in rules.species or name in rules.learnsets:raise ValueError('example species cannot overwrite existing definition')
  ls=deepcopy(rules.learnsets[old]);links=deepcopy(rules.learnset_links[old])
  provenance={'rule_id':SOURCE,'base_species':base['id'],'definition_id':uid,
              'definition_sha256':_FINGERPRINTS.json_fingerprint(definition, sort_keys=True, compact=False, allow_nan=True)}
  sp.update(id=uid,name=name,eng=definition['display_name'],source='core_example',
            _source={'file':'ch11-running-the-game.md','line_span':definition['lines']},
            example_definition=provenance)
  if 'types' in definition:sp['types']=list(definition['types'])
  for stat,delta in definition.get('base_stat_deltas',{}).items():
   if stat not in sp['base_stats'] or type(delta) is not int:raise ValueError('explicit base-stat delta required')
   sp['base_stats'][stat]+=delta
   if sp['base_stats'][stat]<1:raise ValueError('example base stat must remain positive')
  for key,delta in definition.get('movement_deltas',{}).items():
   if key not in sp['movement'] or type(delta) is not int:raise ValueError('explicit capability delta required')
   sp['movement'][key]+=delta
   if sp['movement'][key]<0:raise ValueError('example movement/power cannot be negative')
  if definition.get('size_from'):sp['size']=rules.species[definition['size_from']]['size']
  ls.update(id='learnset/'+uid,species=name,example_definition=deepcopy(provenance),
            size=sp['size'],_source=deepcopy(sp['_source']))
  links.update(id='learnset-links/'+uid,species=name,_source=deepcopy(sp['_source']),
               example_definition=deepcopy(provenance))
  # Natural lists include level-up, egg and only (N) Tutor moves. Other Tutor
  # compatibility and the base specimen's machine list are not widened here.
  for donor_id in definition.get('natural_and_ability_sources',[]):
   donor=rules.species[donor_id]['name'];other=rules.learnsets[donor]
   natural=[r for r in rules.learnset_links[donor].get('moves',[]) if r.get('source') in ('level_up','egg')]
   links['moves']=union(links.get('moves',[]),natural)
   ls['level_up']=union(ls.get('level_up',[]),other.get('level_up',[]))
   ls['egg']=union(ls.get('egg',[]),other.get('egg',[]))
   ls['tutor']=union(ls.get('tutor',[]),[x for x in other.get('tutor',[]) if '(N)' in str(x)])
   for slot,abilities in other.get('abilities',{}).items():
    ls.setdefault('abilities',{})[slot]=union(ls.get('abilities',{}).get(slot,[]),abilities)
  for code,row in machines.items():
   if row['kind']!='TM':continue
   try:mid=rules.move_id(row['move_name'])
   except ExcludedRuleSelection:continue  # Optional compatibility never admits excluded moves.
   if mid is not None and rules.move(mid)['type'] in definition.get('additional_tm_types',[]):
    ls['tm']=union(ls.get('tm',[]),[str(row['number'])+' '+row['move_name']])
  if definition.get('initial_moves'):
   for mid in definition['initial_moves']:
    if rules.move_id(mid)!=mid:raise ValueError('example initial move is unresolved')
   sp['example_initial_moves']=list(definition['initial_moves'])
   # The example itself establishes these known natural moves from birth.
   links['moves']=union(links.get('moves',[]),[{'to':mid,'source':'level_up','level':1} for mid in definition['initial_moves']])
   ls['level_up']=union(ls.get('level_up',[]),[{'level':1,'move':rules.move(mid)['name'],'type':rules.move(mid)['type']} for mid in definition['initial_moves']])
  if definition.get('cannot_evolve'):
   ls['evolution']=['1 - '+name];sp['example_cannot_evolve']=True
  else:
   ls['evolution']=[str(value).replace(old,name) for value in ls.get('evolution',[])]
  prepared.append((sp,ls,links,deepcopy(rules.species_skills.get(old,{}))))
 for sp,ls,links,skills in prepared:
  rules.species[sp['id']]=sp;rules.learnsets[sp['name']]=ls
  rules.learnset_links[sp['name']]=links;rules.species_skills[sp['name']]=skills
 rules.example_species={row['id']:deepcopy(row) for row in data['definitions']}
 rules.example_defender_types=defenders

def require(rules,species):
 record=species.get('example_definition')
 if not record:return
 if rules._selected_rule(SOURCE)!=SOURCE:raise ValueError('example species source is no longer selected')
 definition=getattr(rules,'example_species',{}).get(species['id'])
 if definition is None or record['definition_id']!=species['id']:raise ValueError('example species has no reviewed definition')
 digest=_FINGERPRINTS.json_fingerprint(definition, sort_keys=True, compact=False, allow_nan=True)
 if digest!=record['definition_sha256']:raise ValueError('example species definition changed')

def harmful_move(rules,mid):
 """Read selected damage/effect semantics, not Move names or Status class.

 This learning restriction concerns harm to others. Self costs and conditions
 on healing/protection do not turn those Moves into offensive Status Moves.
 Native lifecycle markers retain their existing owner's reviewed declarations.
 """
 if mid=='struggle':return False  # Universal Struggle is not a learned Move.
 move=rules.move(mid)
 if move.get('class') in ('물리','특수') or move.get('damage_base') not in (None,0):return True
 import effect_contracts as EFFECTS
 def offensive(value):
  if isinstance(value,list):return any(offensive(row) for row in value)
  if not isinstance(value,dict):return False
  kind=value.get('type')
  if kind=='declarative_move_contract':
   import declarative_move_contracts as DECLARATIVE
   row=DECLARATIVE.definition(rules,value['source'])
   if row is None or row['operation']!=value['operation']:raise ValueError('reviewed Move lifecycle declaration required')
   return offensive(row['expected_effects'])
  default='self' if kind in EFFECTS.SELF_DEFAULT else 'target'
  target=value.get('target',value.get('on',default))
  others=target not in ('self','user')
  if kind=='ability_transition':
   import ability_transitions as ABILITIES
   row=ABILITIES.definition(rules,value['contract'])
   if row is None:raise ValueError('pacifist needs reviewed ability-transition semantics')
   return row['mode'] in ('suppress','replace','swap')
  if kind=='set_weather':
   weather=rules.mech('combat/weather')['weathers'].get(value.get('weather'))
   if weather is None:raise ValueError('pacifist needs reviewed weather harm semantics')
   return bool(weather.get('tick_damage'))
  if kind in ('swap_items','steal_item','item_drop','transfer_status','execute','hp_share','reaction_attack','copy_move','random_move','repeat_last_move'):return True
  if kind=='copy_stages':return value.get('to','self')!='self'
  if kind=='apply_coat' and '자신' not in str(move.get('range')) and value.get('target')!='self':
   raise ValueError('pacifist needs reviewed Coat harm semantics: '+mid)
  if others:
   if kind in ('apply_status','apply_status_random','hp_loss','damage','fixed_damage','move_lock','forbid','forced_movement','push','bind','control'):return True
   if kind=='custom_condition':
    import custom_condition_effects as CONDITIONS
    row=CONDITIONS.definition(rules,mid)
    if row is None:raise ValueError('pacifist needs reviewed custom-condition harm semantics: '+mid)
    if row['payload'].get('operation') in ('healing_gain_block','seed_drain','perish_count','known_move_lock'):return True
    raise ValueError('pacifist needs reviewed custom-condition harm semantics: '+mid)
   amount=value.get('delta') if kind=='stage_change' else value.get('value')
   if kind in ('stage_change','stat_mod','accuracy_mod','evasion_mod','save_mod') and isinstance(amount,(int,float)) and amount<0:return True
  understood={'apply_status','apply_status_random','hp_loss','damage','fixed_damage','move_lock','forbid','forced_movement','push','bind','control',
   'custom_condition','stage_change','stat_mod','accuracy_mod','evasion_mod','save_mod','heal','full_restore','delayed_heal','self_hp_set',
   'cure_status','cure_all_status','temp_hp','blessing','reaction_shield','damage_reduction','grant_capability','targeting_rule','immunity_rule',
   'never_miss','item_restore','copy_stages','next_roll_bonus','damage_roll_mod','apply_coat','field_effect','rule','note'}
  if kind is not None and kind not in understood:raise ValueError('pacifist needs reviewed effect harm semantics: '+str(kind))
  return any(offensive(row) for key,row in value.items() if key not in ('_src','_rule_id','_rule_source'))
 mechanics,_=rules.move_mech(mid)
 if mechanics.get('apply_status') is not None:return True
 if isinstance(mechanics.get('evasion_mod'),(int,float)) and mechanics['evasion_mod']<0:return True
 if set(mechanics)-{'apply_status','effects_exec','evasion_mod','never_miss'}:raise ValueError('pacifist needs reviewed Move harm semantics: '+mid)
 if not mechanics:raise ValueError('pacifist needs reviewed Move harm semantics: '+mid)
 return offensive(mechanics)

def learning_allowed(rules,species,mid):
 if not species.get('example_definition'):return True
 require(rules,species)
 definition=rules.example_species[species['id']]
 return not definition.get('cannot_learn_harmful_moves') or not harmful_move(rules,mid)

def validate_spec(rules,spec,*,moves=None):
 record=spec.get('example_definition')
 species=rules.species.get(spec.get('species'),{})
 expected=species.get('example_definition')
 if expected is None:
  if record is not None:raise ValueError('example provenance does not match actual species')
  return
 require(rules,species)
 if record!=expected:raise ValueError('source-derived species requires exact reviewed provenance')
 for raw in spec.get('moves',[]) if moves is None else moves:
  mid=raw if raw=='struggle' else rules.move_id(raw)
  if mid is not None and not learning_allowed(rules,species,mid):raise ValueError('pacifist example cannot learn a harmful Move: '+mid)

def resolved_basic_choices(rules,species,choices):
 # A derived example can expose donor choices missing from the selected corpus.
 # Preserve its complete choice pool; the automatic initial choice needs an
 # actual selected identity. Explicit caller selections keep normal validation.
 if not species.get('example_definition'):return choices
 result=[]
 for name in choices:
  if name in rules.excluded_abilities:continue
  try:rules.selection.resolve_name(name,('ability/',))
  except (KeyError,ValueError):continue
  result.append(name)
 if choices and not result:raise ValueError('example needs an explicit available initial ability')
 return result

