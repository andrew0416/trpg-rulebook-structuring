"""Explicit, sparing regional adaptations; never change every base-species actor.

Definitions use the existing selected custom-species loader and builder. This
adapter records the ecological choice and creates one actual individual with a
new identity. Regional description itself creates no mechanical bonus.
"""
from copy import deepcopy
import hashlib,json
import common_checks as C
from builder import build_pokemon,species_lookup

SOURCE='ch11-running-the-game/포켓몬으로-가득찬-세상/합리적인-생태계'

import resolution_transaction as _FINGERPRINTS

def source(e):
 if e.r._selected_rule(SOURCE)!=SOURCE:raise ValueError('selected regional-adaptation source requires its own policy')

def _text(value,name):
 if not isinstance(value,str) or not value.strip():raise ValueError(name+' required')
 return value

def _selected_variant(e,key):
 sp=species_lookup(e.r,key)
 if sp.get('source')!='custom' or sp['id'] not in e.r.custom_species:raise ValueError('explicitly loaded custom regional species required')
 marker={'id':sp['id'],'title':sp['name'],'source':{'file':'data/custom/species/'+sp['custom_file']}}
 if not e.r.ruleset.allows(marker)[0]:raise ValueError('regional definition source is not selected')
 return sp

def _signature(e,sp):
 data={'species':sp,'learnset':e.r.learnsets.get(sp['name']),'skills':e.r.species_skills.get(sp['name'])}
 return _FINGERPRINTS.json_fingerprint(data, sort_keys=True, compact=False, allow_nan=True)

def create(e,actor,*,base_species,variant_species,individual_id,name,level,region,ecological_context,rarity_reason,reason,nature=None,abilities=None):
 import pokemon_activities as P
 import world_entities as WORLD
 from engine import Combatant
 P._trainer(actor);P._outside(e);source(e)
 base=species_lookup(e.r,base_species);variant=_selected_variant(e,variant_species)
 if base['id']==variant['id']:raise ValueError('regional variant must remain distinct from its base species')
 for value,label in ((individual_id,'new actual individual identity'),(name,'individual name'),(region,'specific region'),(ecological_context,'ecological adaptation context'),(rarity_reason,'reason to use this optional adaptation sparingly'),(reason,'GM deliberate variant adoption')):_text(value,label)
 C.integer(level,'actual Pokemon level',1,100)
 if individual_id in WORLD.entity_index(e):raise ValueError('individual identity already exists; regional choice cannot stack')
 pools=e.r.learnsets[variant['name']].get('abilities',{})
 if abilities is None:raise ValueError('explicit initial regional ability selection required')
 if abilities is not None:
  if not isinstance(abilities,(list,tuple)) or not abilities or len(set(abilities))!=len(abilities):raise ValueError('explicit distinct regional ability choices required')
  # Initial factory only chooses the ordinary Basic slot; later growth owns later slots.
  if len(abilities)!=1 or abilities[0] not in pools.get('기본 특성',[]):raise ValueError('initial regional ability must be a listed Basic option')
  for ability in abilities:
   uid=e.r.selection.resolve_name(ability,('ability/',));e.r.selection.require_supported_version(uid)
 spec=build_pokemon(e.r,variant['id'],level,name=name,nature=nature,abilities=abilities)
 spec['id']=individual_id
 spec['regional_variant']={'source':SOURCE,'base_species':base['id'],'variant_species':variant['id'],'definition_file':variant['custom_file'],'definition_signature':_signature(e,variant),
   'region':region,'ecological_context':ecological_context,'rarity_reason':rarity_reason,'reason':reason,
   'base_reference':{'skills':deepcopy(e.r.species_skills.get(base['name'],{})),'movement':deepcopy(base.get('movement',{})),'capabilities':deepcopy(base.get('capabilities',[]))},
   'appearance':deepcopy(e.r.learnsets[variant['name']].get('note',''))}
 target=Combatant(e.r,spec)
 # Construction does not take a turn, enter combat, roll an effect, or register a held item.
 target.on_field=False
 e.gm.everyone.append(target)
 if getattr(e,'everyone',None) is not e.gm.everyone:e.everyone.append(target)
 return target

def validate_actor(e,target):
 row=target.spec.get('regional_variant')
 if row is None:return
 source(e)
 if row.get('source')!=SOURCE or row.get('variant_species')!=target.spec.get('species'):raise ValueError('regional individual/source identity changed')
 sp=_selected_variant(e,row['variant_species'])
 if sp.get('custom_file')!=row.get('definition_file') or _signature(e,sp)!=row.get('definition_signature'):raise ValueError('regional source definition changed')

ACTIVITIES={'create_regional_pokemon':create}

