"""PTK advisory inputs for native checks; no inferred DC or player knowledge.

The host supplies the GM's decisions. This module preserves their reasons and
uses existing check results. It neither creates world effects nor a display UI.
"""
from copy import deepcopy
from dataclasses import replace
from pathlib import Path
import json
import common_checks as C
import skill_modifiers as S

def policy(e):
 return json.loads((Path(e.r.root)/'data/adjudication-guidance.json').read_text(encoding='utf-8'))

def _text(value,name):
 if not isinstance(value,str) or not value.strip():raise ValueError('nonempty '+name+' required')
 return value

def difficulty(e,selected_dc,context):
 if context is None:return None
 if not isinstance(context,dict) or set(context)-{'reference_rank','tone','realism','task_context','reason'}:raise ValueError('explicit GM difficulty context required')
 _text(context.get('reason'),'GM difficulty reason')
 for key,value in context.items():_text(value,key)
 if selected_dc is not None:C.integer(selected_dc,'selected DC')
 guide=policy(e);rank=context.get('reference_rank')
 if rank is not None and rank not in guide['rank_dc_guide']:raise ValueError('unknown printed DC guide rank')
 return {'source':guide['source'],'selected_dc':selected_dc,'context':deepcopy(context),'reference_dc':guide['rank_dc_guide'].get(rank),'reference_is_guidance':True}

def disagreement(e,value,selection):
 if value is None:return None
 if not isinstance(value,dict) or set(value)!={'player_reason','gm_reason'}:raise ValueError('disagreement needs player and GM reasons')
 for key,text in value.items():_text(text,key)
 return dict(deepcopy(value),guidance=policy(e)['disagreement'],current_gm_selection=deepcopy(selection))

def _responses(value):
 if value is None:return {}
 if not isinstance(value,dict) or not value or set(value)-{'success','failure'}:raise ValueError('GM responses must use success/failure keys')
 for text in value.values():_text(text,'GM disclosed knowledge or failure consequence')
 return deepcopy(value)

def knowledge(e,actor,target,topic,*,species_known=None,method=None,reason=None,dc=None,
              high_rank_requirement=None,pokedex_has_entry=None,responses=None,device_selection=None,**roll_options):
 config=policy(e)['knowledge']
 if actor is None or actor.r is not e.r or actor.kind!='trainer':raise ValueError('actual trainer in this rule context required')
 if target is None or target.r is not e.r or target.kind!='pokemon':raise ValueError('actual Pokemon subject in this rule context required')
 if target not in list(e.everyone or [])+list(e.gm.everyone or []):raise ValueError('registered actual Pokemon subject required')
 topics=config['basic_topics']+config['additional_topics']+config['specific_topics']
 if topic not in topics:raise ValueError('supported concrete Pokemon knowledge topic required')
 if species_known is not None and type(species_known) is not bool:raise ValueError('species familiarity is an explicit GM boolean')
 if pokedex_has_entry is not None and type(pokedex_has_entry) is not bool:raise ValueError('Pokedex entry availability is an explicit GM boolean')
 if method not in (None,'known','skill','pokedex'):raise ValueError('knowledge method must be known/skill/pokedex')
 if device_selection is not None and method!='pokedex':raise ValueError('physical Pokedex selection belongs only to the Pokedex knowledge path')
 answers=_responses(responses)
 if set(roll_options)&{'mode','outcome','description','cost','failure_margin_accepted'}:raise ValueError('knowledge consequences use explicit responses')
 if e.r._selected_rule('ch03-skills-edges-feats/스킬/포켓몬학')!='ch03-skills-edges-feats/스킬/포켓몬학':raise ValueError('selected Pokemon Education source needs its own knowledge policy')
 rank=S.effective_rank(e.r,actor,'포켓몬학')
 basis={'knowledge':{'source':config['source'],'topic':topic,'subject_id':target.spec.get('id',target.name),
  'reference_species':target.spec.get('species'),'species_known':species_known,'education_rank':rank,
  'information_origin':'explicit GM disclosure; no automatic private sheet/species lookup',
  'species_expectation_is_not_individual_state':True}}
 def pending(needed):return C.PendingDecision(needed,basis=deepcopy(basis))
 if actor.dead or actor.fainted or actor.hp<=0:return pending('source for unconscious knowledge action')
 ordinary_basic=topic in config['basic_topics'] and species_known is True and rank>=config['ordinary_basic_minimum_rank']
 if method is None:
  if ordinary_basic:method='known'
  else:return pending('GM/group knowledge agreement and known/skill/Pokedex method; no automatic DC')
 if not ordinary_basic or method!='known':_text(reason,'GM knowledge access reason')
 basis['knowledge'].update(method=method,reason=reason)
 if topic in config['specific_topics'] and method!='pokedex':
  if high_rank_requirement is None:return pending('GM selects the high Pokemon Education rank threshold; source has no fixed number')
  C.integer(high_rank_requirement,'GM high-rank requirement',2,8)
  basis['knowledge']['gm_high_rank_requirement']=high_rank_requirement
  if rank<high_rank_requirement:return pending('actual Pokemon Education below this explicit GM requirement; no invented failure cost')
 elif high_rank_requirement is not None:raise ValueError('high-rank threshold belongs only to very specific knowledge without Pokedex')
 if method in ('known','pokedex'):
  if dc is not None or roll_options:raise ValueError('no-roll knowledge must not receive dice/DC/rank-threshold options')
  if method=='known' and pokedex_has_entry is not None:raise ValueError('Pokedex availability only belongs to the Pokedex path')
  if method=='pokedex':
   uid='item/포켓몬-도감'
   if e.r._selected_rule(uid)!=uid:raise ValueError('selected Pokedex version needs its own access policy')
   if device_selection is None:
    inventory=actor.spec.get('items',{})
    owned=[inventory[key] for key in ('포켓몬 도감','포켓몬도감',uid) if key in inventory]
    if len(owned)>1:raise ValueError('ambiguous duplicate Pokedex inventory aliases')
    if not owned or C.integer(owned[0],'owned Pokedex count',0)<1:raise ValueError('actual owned Pokedex required')
   else:
    import pokedex_device as POKEDEX
    entry=POKEDEX.knowledge_entry(e,actor,device_selection,target,topic)
    basis['knowledge']['pokedex_instance_id']=entry['instance_id']
    if entry['answer'] is not None:
     if pokedex_has_entry is None:pokedex_has_entry=True
     if responses is None:answers=_responses({'success':entry['answer']})
   # This reads an existing entry confirmed by the GM; scanning is a distinct Standard action.
   if pokedex_has_entry is not True:return pending('GM confirms this Pokedex contains the requested entry')
  result=e.common_action(actor,mode='no_roll',outcome='success' if 'success' in answers else None,description=answers.get('success'))
 else:
  if pokedex_has_entry is not None:raise ValueError('skill knowledge does not use a Pokedex availability flag')
  if dc is None:return pending('GM knowledge DC; no fixed task DC or automatic failure policy')
  result=e.common_action(actor,'포켓몬학',dc,mode='skill',**roll_options)
  original_basis=deepcopy(result.basis or {})
  if result.check is not None:
   outcome='success' if result.check.passed else 'failure'
   result=C.adjudicate(result.check,outcome=outcome,description=answers.get(outcome),declaration=result.declaration)
   result=replace(result,basis=original_basis)
 inherited=deepcopy(result.basis or {});inherited.update(basis)
 return replace(result,basis=inherited)
