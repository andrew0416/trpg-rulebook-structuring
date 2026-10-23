"""The transform family: source permission, time, inputs and outputs commit together.
The shared interface accepts a typed request; no item-per-class hierarchy is used.
"""
from abc import ABC,abstractmethod
from dataclasses import dataclass
from copy import deepcopy
from typing import Any
from consumable_use import UseFamily,UseAdapter
import crafting_resources as R

@dataclass(frozen=True)
class TransformRequest:
 actor:Any
 options:dict

class TransformationUse(ABC):
 family=UseFamily.TRANSFORM
 operation:str

 def execute(self,engine,request:TransformRequest):
  if not isinstance(request,TransformRequest) or not isinstance(request.options,dict):raise ValueError('typed transformation request required')
  import state_grants as G
  R.validate(request.actor)
  if engine.r._selected_rule(R.SOURCE)!=R.SOURCE:raise ValueError('selected crafting resource rules need their own adapter')
  def commit(e,actor):
   before=R.snapshot(actor);started=e.elapsed_seconds;options=deepcopy(request.options)
   import crafting_products as PRODUCTS
   product_policy=options.pop('product_policy',None);event_id=options.pop('event_id',None)
   plan=PRODUCTS.preflight(e,actor,self.operation,options,product_policy,event_id)
   if 'replay' in plan:return plan['replay']
   result=self.perform(e,actor,options)
   PRODUCTS.materialize(e,actor,result,plan)
   self.bind_product(e,actor,result,plan)
   R.record(e,actor,operation=self.operation,sources=self.sources(e,actor,options,result),started_at=started,before=before,result=result)
   PRODUCTS.publish(e,actor,plan,actor.spec['resource_transformations'][-1])
   return result
  return G.transition(engine,request.actor,commit)

 def bind_product(self,engine,actor,result,plan):
  """Bind source-specific native evidence before the original receipt is published."""
  return None

 @abstractmethod
 def perform(self,engine,actor,options):...

 @abstractmethod
 def sources(self,engine,actor,options,result):...

class NativeCraftingUse(TransformationUse):
 def __init__(self,operation):self.operation=operation

 def perform(self,engine,actor,options):
  import crafting_activities as C
  C._p()._trainer(actor)
  handlers={'cook_poffins':C._cook_poffins,'dismantle':C._dismantle,'craft_item':C._craft_item,'craft_gem':C._craft_gem}
  return handlers[self.operation](engine,actor,**options)

 def sources(self,engine,actor,options,result):
  import crafting_activities as C
  sources=[R.SOURCE]
  if self.operation=='cook_poffins':sources.append('item/포핀-혼합기')
  elif self.operation=='dismantle':sources.append(engine.r.item_effects(options['item'])[1]['id'])
  elif self.operation=='craft_gem':sources.extend((C._p().FEATURES['gem_lore'][0],'item/조각',engine.r.item_effects(result['item'])[1]['id']))
  else:
   sources.extend((result['recipe_source'],result['item_id']))
  return list(dict.fromkeys([*sources,*result.get('recipe_sources',[])]))

ADAPTERS:dict[str,UseAdapter[TransformRequest]]={name:NativeCraftingUse(name) for name in ('cook_poffins','dismantle','craft_item','craft_gem')}

def dispatch(engine,actor,operation,**options):
 return ADAPTERS[operation].execute(engine,TransformRequest(actor,options))
