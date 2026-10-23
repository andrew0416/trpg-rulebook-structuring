"""Source-defined sensory and qualitative traits, derived from live ownership.
No second state registry, invented temperature or inferred heat/cold damage.
"""
import state_grants as G
import skill_modifiers as S

DEFINITIONS={
 'blindsense':('capability/맹인-감각',('맹인 감각','Blindsense'),19),
 'darkvision':('capability/암흑시야',('암흑시야','Darkvision'),27),
 'chilled':('capability/차가움',('차가움','Chilled'),25),
 'heater':('capability/따끈따끈',('따끈따끈','Heater'),59),
 'bloom':('capability/만개',('만개','Bloom'),21),
 'weathershape':('capability/날씨-형상',('날씨 형상','Weathershape'),154),
}
BLINDNESS=('실명','완전 실명','완전-실명')


def owned(actor):
 names={S.key(x) for x in G.effective_capabilities(actor,only=tuple(alias for _,aliases,_ in DEFINITIONS.values() for alias in aliases))}
 result={}
 for name,(source,aliases,line) in DEFINITIONS.items():
  if not names.intersection(S.key(x) for x in aliases):continue
  if actor.r._selected_rule(source)!=source:raise ValueError('selected capability trait needs its own policy')
  result[name]={'source':source,'anchor':'input/ch10-index-reference.md:'+str(line)}
 return result


def projection(actor, *, engine=None):
 import perception_observe as OBSERVE
 return OBSERVE.traits(actor,engine=engine)


def _projection(actor, *, engine=None):
 facts=owned(actor);blind='blindsense' in facts
 bloom=None;weathershape=None
 if 'bloom' in facts or 'weathershape' in facts:
  if engine is None:raise ValueError('Weather appearance requires actual battlefield weather')
  import weather_state as WEATHER
  WEATHER.validate(engine)
  occurrence=WEATHER.effective_state(engine,actor)['active']
  effective=occurrence['weather'] if occurrence else None
  if engine.weather is not None and getattr(engine,WEATHER.KEY,{}).get('active') is None:raise ValueError('Weather appearance requires sourced weather')
  context={'weather':effective,'weather_source':occurrence['source_id'] if occurrence else None,
           'weather_occurrence_id':occurrence.get('id',occurrence.get('request_id')) if occurrence else None}
  if 'bloom' in facts:
   sunny=effective=='sunny'
   bloom=dict(context,source=facts['bloom']['source'],form='sunshine' if sunny else 'overcast',
              appearance='pink flower' if sunny else 'purple bud')
  if 'weathershape' in facts:
   # Source defines four weather appearances, not a default color or type change.
   color={'sunny':'orange','rain':'blue and grey','hail':'light blue','sandstorm':'rocky brown'}.get(effective)
   weathershape=dict(context,source=facts['weathershape']['source'],appearance=color)

 return {'entity_id':actor.entity_id,'blindsense':blind,'darkvision':blind or 'darkvision' in facts,
         'visual_reading':False if blind else None,'color_discrimination':False if blind else None,
         'thermal_descriptions':[value for name,value in (('chilled','cold'),('heater','warm')) if name in facts],
         'temperature':None,'contact_damage':None,'bloom_appearance':bloom,'weathershape_appearance':weathershape,'sources':facts}


def immunity(actor,condition,*,cause=None):
 if condition not in BLINDNESS:return None
 facts=owned(actor)
 if 'blindsense' in facts:return facts['blindsense']['source']
 if cause=='darkness' and 'darkvision' in facts:return facts['darkvision']['source']
 return None


def blindness_cause(condition,parameters):
 if condition not in BLINDNESS or parameters is None:return None
 if not isinstance(parameters,dict) or set(parameters)!={'cause'} or parameters['cause'] not in ('darkness','external'):
  raise ValueError('Blindness cause must be explicit darkness or external')
 return parameters['cause']
