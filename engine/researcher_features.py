"""Researcher source-bound training effects (ch04:2066,2127).

Training produces a single pushed skill on each actual owned Pokemon. Native
dice plans distinguish the base rank/pool from added dice and fixed modifiers.
"""
from copy import copy,deepcopy
from dataclasses import dataclass
import re
import common_checks as C
import skill_modifiers as S
import contest_features as FEATURES

SOURCE='ch04-trainer-classes/프로페셔널-클래스/연구원-연구-분야'
POKEMON_SKILLS='ch05-pokemon/포켓몬-관리하기/스킬'
RESEARCHER='class/연구원'
PUSHER='feat/후원자'
SKILL_TRAINER='feat/스킬-트레이너'
FIELDS={'general','apothecary','artificer','botany','chemistry','climatology','occultism','paleontology','pokemon_caretaking'}

def source(e):
 if e.r._selected_rule(SOURCE)!=SOURCE:raise ValueError('selected Researcher field variant needs a sourced adapter')

FIELD_ALIASES=dict(zip(('일반 지식','약사','기능공','식물학','화학','기후학','신비학','고생물학','포켓몬 관리'),('general','apothecary','artificer','botany','chemistry','climatology','occultism','paleontology','pokemon_caretaking')))

def field_id(value):
 if not isinstance(value,str):raise ValueError('known Researcher field name required')
 canonical=FIELD_ALIASES.get(value,value)
 if canonical not in FIELDS:raise ValueError('known Researcher field name required')
 return canonical

def research_fields(actor):
 """Normalize the existing two-field legacy record and acquired branch pairs.
 Both may be present only when they describe exactly the same acquired fields.
 This validation never creates a field choice or changes stored acquisition.
 """
 choices=actor.spec.get('feature_choices',{})
 if not isinstance(choices,dict):raise ValueError('acquired feature choices must be a mapping')
 pairs=choices.get(RESEARCHER);legacy=actor.spec.get('research_fields');selected=None
 if pairs is not None:
  if not isinstance(pairs,(list,tuple)) or not pairs:raise ValueError('actual acquired Researcher field pairs required')
  selected=[]
  for pair in pairs:
   if not isinstance(pair,(list,tuple)) or len(pair)!=2:raise ValueError('each Researcher acquisition chooses two fields')
   selected.extend(field_id(x) for x in pair)
  if len(set(selected))!=len(selected):raise ValueError('repeated acquired Researcher fields')
 if legacy is not None:
  if not isinstance(legacy,(list,tuple)) or len(legacy)!=2:raise ValueError('legacy Researcher record requires exactly two acquired fields')
  normalized=[field_id(x) for x in legacy]
  if len(set(normalized))!=2:raise ValueError('two distinct acquired Researcher fields required')
  if selected is not None and set(selected)!=set(normalized):raise ValueError('conflicting legacy and canonical acquired Researcher fields')
  if selected is None:selected=normalized
 if selected is None:raise ValueError('actual acquired Researcher fields required')
 return tuple(selected)

def researcher(e,actor,field):
 import acquired_features as ACQUIRED
 ACQUIRED.validate_class_slots(actor)
 FEATURES.conscious_trainer(actor);source(e)
 if not FEATURES.owned(actor,RESEARCHER) and 'Researcher' not in list(actor.spec.get('classes',[]))+list(actor.spec.get('feats',[])):
  raise ValueError('actual acquired Researcher class required')
 if e.r._selected_rule(RESEARCHER)!=RESEARCHER:raise ValueError('selected Researcher class needs its own sourced adapter')
 selected=research_fields(actor)
 if field_id(field) not in selected:raise ValueError('feature requires its acquired Researcher field')
 if max(S.rank(e.r,actor,skill)[2] for skill in sorted(S.EDUCATION_SKILLS))<3:raise ValueError('Researcher requires a Novice Education skill')
 return selected

def require(e,actor,uid,field):
 researcher(e,actor,field)
 if not FEATURES.owned(actor,uid):raise ValueError('actual acquired Researcher feature required: '+uid)

def prepare_training(e,actor,targets,choices):
 if choices is None:return None
 require(e,actor,PUSHER,'pokemon_caretaking');require(e,actor,SKILL_TRAINER,'pokemon_caretaking')
 if S.rank(e.r,actor,'포켓몬학')[2]<3:raise ValueError('Pusher requires Novice Pokemon Education')
 if not isinstance(choices,dict):raise ValueError('one explicit pushed skill per trained Pokemon required')
 ids=[target.spec.get('id') for target in targets]
 if any(not isinstance(uid,str) or not uid for uid in ids) or len(set(ids))!=len(ids) or set(choices)!=set(ids):
  raise ValueError('pushed skill choices must match every actual trained Pokemon')
 selected=[]
 for target in targets:
  FEATURES.owner(actor,target)
  skill=S.skill_id(e.r.skill_policy,choices[target.spec['id']],required=True)
  selected.append((target,skill))
 probe=copy(e);probe.log_lines=[]
 shadow=copy(actor);shadow._action_history=deepcopy(getattr(actor,'_action_history',[]))
 FEATURES.trigger_free_action(probe,shadow,SKILL_TRAINER)
 return selected

def finish_training(e,actor,plan,training_source):
 if plan is None:return
 FEATURES.trigger_free_action(e,actor,SKILL_TRAINER)
 for target,skill in plan:
  target.spec['pushed_skill']={'source':SOURCE,'feature':SKILL_TRAINER,'trainer_id':actor.spec['id'],
      'skill':skill,'training_source':training_source,'completed_at':e.elapsed_seconds}
 e.log('  '+actor.name+': 실제 훈련한 포켓몬의 선택 스킬을 다음 연장 휴식까지 강화',SOURCE)

def extended_rest(actor):
 actor.spec.pop('pushed_skill',None)

def native_plan(e,actor,skill):
 if actor.kind!='pokemon':return None
 if e.r._selected_rule(POKEMON_SKILLS)!=POKEMON_SKILLS:raise ValueError('selected Pokemon skill version needs a native pool adapter')
 canonical=S.skill_id(e.r.skill_policy,skill)
 values=[value for key,value in actor.spec.get('skills',{}).items() if S.skill_id(e.r.skill_policy,key)==canonical]
 parsed=[]
 for value in values:
  match=re.fullmatch(r'\s*([1-9][0-9]*)d6\s*([+-]\s*[0-9]+)?\s*',value) if isinstance(value,str) else None
  if match:parsed.append((int(match[1]),int((match[2] or '0').replace(' ',''))))
  else:parsed.append((S.rank(e.r,actor,skill)[2],0))
 if len(set(parsed))>1:raise ValueError('conflicting Pokemon skill pool aliases')
 import csv_item_form_contracts as CSV_FORMS
 projected=CSV_FORMS.skill_pool_projection(actor,canonical)
 if projected is not None:parsed=[projected]
 if parsed:
  n,bonus=parsed[0]
  import baby_templates as BABY
  n=max(1,n-BABY.skill_rank_penalty(actor))
 else:n,bonus=S.rank(e.r,actor,skill)[2],0
 name='포켓몬 스킬';count=n
 pushed=actor.spec.get('pushed_skill')
 if pushed is not None:
  if not isinstance(pushed,dict) or pushed.get('source')!=SOURCE or pushed.get('feature')!=SKILL_TRAINER:
   raise ValueError('pushed skill requires its actual training source')
  if pushed.get('trainer_id')!=actor.spec.get('trainer_id'):
   raise ValueError('pushed skill source no longer belongs to the current owner')
  if S.skill_id(e.r.skill_policy,pushed.get('skill'),required=True)==canonical:
   source(e)
   if n<6:count+=1
   else:bonus+=3
 return {'rank':n,'dice_count':count,'modifier':bonus,'rank_name':name,'expression':str(count)+'d6',
         'pushed':bool(pushed and S.skill_id(e.r.skill_policy,pushed['skill'])==canonical)}

@dataclass(frozen=True)
class PokemonSkillRoll(C.SkillRoll):
 dice_count: object=None
 def __post_init__(self):
  C.integer(self.rank,'base Pokemon skill dice',1)
  count=self.rank if self.dice_count is None else C.integer(self.dice_count,'actual Pokemon skill dice',1)
  C.validate_request(1,self.modifier,self.helper_rank,len(self.penalties),self.helper_bonus)
  object.__setattr__(self,'faces',C.dice(self.faces,count))
  object.__setattr__(self,'penalties',C.dice(self.penalties))



FOSSIL_RESTORATION='feat/화석-복원'
PREHISTORIC_BOND='feat/선사의-결속'
CROWN_PREFIX='relic-crown/'
RELIC_NAMES={'hp':'왕관 유물','atk':'원시의 틀','def':'선사 면도칼','spa':'원시의 망토','spd':'선사 방패','spe':'띠 유물'}

def _relic_prefix(stat):
 import researcher_fields as FIELDS
 return FIELDS.DEFINITIONS[FIELDS.BOND]['relics'][stat]['prefix']

def craft_relic(e,actor,pokemon,*,relic,minutes,tie_stat=None,tie_reason=None):
 """Prehistoric Bond: one held item from the restored remains, keyed to the individual's highest nature-adjusted base stat."""
 from builder import species_lookup,nature_base
 import pokemon_activities as P
 import action_lifecycle as ACTION
 import turn as TURN
 if relic not in RELIC_NAMES:raise ValueError('relic stat required: hp, atk, def, spa, spd or spe')
 if e.encounter_active:raise ValueError('relic production is an Extended Action outside combat')
 require(e,actor,FOSSIL_RESTORATION,'paleontology');require(e,actor,PREHISTORIC_BOND,'paleontology')
 P._feature(e,actor,'paleontologist')
 if S.rank(e.r,actor,'포켓몬학')[2]<5:raise ValueError('Prehistoric Bond requires Expert Pokemon Education')
 FEATURES.owner(actor,pokemon);C.integer(minutes,'GM relic Extended Action minutes',1)
 probe=copy(e);probe.log_lines=[]
 if not TURN.can_act(probe,actor) or not ACTION.status_permission(probe,actor,'standard'):raise ValueError('Extended Action currently unavailable')
 import pokemon_entities as EGGS
 egg_id=pokemon.spec.get('fossil_egg_id')
 entry=EGGS.egg_index(e).get(pokemon.spec.get('fossil_egg_entity_id'))
 if entry is None or not entry[1].get('hatched') or entry[1].get('pokemon_id')!=pokemon.entity_id:raise ValueError('actual Pokemon hatched from restored fossil required')
 egg=entry[1];fossil=EGGS.egg_fossil(e,egg)
 if fossil.get('restored_by')!=actor.entity_id:raise ValueError('Relic Crown requires remains that this trainer restored')
 if fossil.get('status')!='hatched' or egg.get('source')!='edge/고생물학자':raise ValueError('native fossil restoration and hatch provenance required')
 if fossil.get('relic_created'):raise ValueError('these actual fossil remains already produced a relic')
 nature=pokemon.spec.get('nature')
 import nature_state as NATURE
 if NATURE.describe(e.r,nature) is None:raise ValueError('known actual nature required')
 base=nature_base(species_lookup(e.r,pokemon.spec['species'])['base_stats'],nature,e.r)
 highest=[stat for stat,value in base.items() if value==max(base.values())]
 if relic not in highest:raise ValueError(RELIC_NAMES[relic]+' requires '+relic+' among the highest nature-adjusted base stats')
 if len(highest)>1:
  if tie_stat!=relic or not isinstance(tie_reason,str) or not tie_reason.strip():raise ValueError('GM must explicitly select the highest base stat and explain the tied-stat choice')
 elif tie_stat not in (None,relic) or tie_reason is not None:raise ValueError('no tied base stat selection is required')
 identity=_relic_prefix(relic)+fossil['entity_id']
 if identity in actor.spec.get('relic_items',{}):raise ValueError('relic instance already exists')
 e.advance_time(minutes*60,[actor,pokemon])
 record={'id':identity,'source':SOURCE,'feature':PREHISTORIC_BOND,'maker_id':actor.spec['id'],'pokemon_id':pokemon.spec['id'],
         'egg_id':egg_id,'egg_entity_id':egg['entity_id'],'fossil_id':egg['fossil_id'],'fossil_entity_id':fossil['entity_id'],'base_stats_with_nature':base,'highest_stats':highest,'selected_stat':relic,
         'tie_reason':tie_reason,'created_at':e.elapsed_seconds}
 actor.spec.setdefault('relic_items',{})[identity]=deepcopy(record)
 actor.spec.setdefault('items',{})[identity]=1
 pokemon.spec.setdefault('relic_sources',{})[identity]=deepcopy(record)
 fossil['relic_created']=identity
 e.log('  '+actor.name+': 복원한 개별 포켓몬의 '+RELIC_NAMES[relic]+' 제작',SOURCE)
 return deepcopy(record)

def craft_relic_crown(e,actor,pokemon,*,minutes,tie_stat=None,tie_reason=None):
 return craft_relic(e,actor,pokemon,relic='hp',minutes=minutes,tie_stat=tie_stat,tie_reason=tie_reason)

def relic_effects(e,pokemon,name):
 import researcher_fields as FIELDS
 found=FIELDS.relic_definition(name)
 if found is None:return None
 stat,definition=found
 source(e)
 record=pokemon.spec.get('relic_sources',{}).get(name)
 header={'id':name,'category':'지니는 도구','desc':'복원한 개별 포켓몬 전용 '+RELIC_NAMES[stat]}
 if not record or pokemon.kind!='pokemon' or record.get('pokemon_id')!=pokemon.spec.get('id') or (record.get('egg_entity_id')!=pokemon.spec.get('fossil_egg_entity_id') if record.get('egg_entity_id') is not None else record.get('egg_id')!=pokemon.spec.get('fossil_egg_id')):
  return [],header
 if record.get('source')!=SOURCE or record.get('feature')!=PREHISTORIC_BOND or record.get('selected_stat')!=stat:raise ValueError('unresolved relic provenance')
 return deepcopy(FIELDS.relic_effects(stat)),header

def equip_relic(e,actor,pokemon,identity):
 import items as ITEMS
 FEATURES.owner(actor,pokemon)
 record=actor.spec.get('relic_items',{}).get(identity)
 if not record or record.get('pokemon_id')!=pokemon.spec.get('id'):raise ValueError('this relic is bound to another restored individual')
 if actor.spec.get('items',{}).get(identity,0)!=1:raise ValueError('owned unspent relic instance required')
 import held_equipment as HELD
 if HELD.any_held(pokemon) or getattr(pokemon,'_item_reg',{}):raise ValueError('Pokemon held-item slot must be empty')
 effect=relic_effects(e,pokemon,identity)
 if effect is None or not effect[0]:raise ValueError('relic has no effect on this Pokemon')
 ITEMS.register_item(e,pokemon,identity)
 if identity not in getattr(pokemon,'_item_reg',{}):raise ValueError('relic registration failed')
 pokemon.item=identity;pokemon.spec['item']=identity
 actor.spec['items'][identity]-=1
 return identity

def equip_relic_crown(e,actor,pokemon,identity):
 return equip_relic(e,actor,pokemon,identity)
