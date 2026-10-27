"""PTK trainer base capabilities; live ranks, explicit current/base distinction."""
import arithmetic_policy as M
import skill_modifiers as S
import physical_limits as LIMITS

SOURCE='ch02-character-creation/트레이너-제작/스텝-6-파생-능력치-찾기'
DERIVED={'land','high_jump','long_jump','swim'}
# Core pp16/18 and the Korean quick summary agree; preserve earlier explicit choices.
CORE_POWER_POLICY='core1.05:p16+p18'

def source(c):
 if c.r._selected_rule(SOURCE)!=SOURCE:raise ValueError('selected trainer capability variant needs its own source policy')

def values(c):
 if c.kind!='trainer':raise ValueError('trainer-base capability derivation requires a trainer')
 source(c)
 acrobatics=S.effective_rank(c.r,c,'곡예');athletics=S.effective_rank(c.r,c,'육상')
 choices=traveler_choices(c);survival=S.effective_rank(c.r,c,'생존')
 jump_rank=survival if 'jump' in choices else acrobatics
 land_ranks=(max(athletics,acrobatics),survival) if 'land' in choices else (athletics,acrobatics)
 return jump_bonuses(c,{'high_jump':int(jump_rank>=4)+int(jump_rank>=6),'long_jump':M.ratio(jump_rank,2),'land':M.ratio(sum(land_ranks),2)+3})

def for_jump(c,base,*,running_start=False,running_reason=None,running_bonus_included=None):
 if type(running_start) is not bool:raise ValueError('running-start world fact must be explicit boolean')
 result=dict(base)
 if not running_start:
  if running_reason is not None or running_bonus_included is not None:raise ValueError('running details require an actual running start')
  return result
 if c.kind!='trainer':raise ValueError('trainer running-jump bonus cannot be invented for a Pokemon')
 source(c)
 if not isinstance(running_reason,str) or not running_reason.strip():raise ValueError('GM reason establishing actual running start required')
 derived=c.spec.get('movement_basis')=='trainer_base'
 if derived:
  if running_bonus_included not in (None,False):raise ValueError('derived base values do not yet include running')
 elif type(running_bonus_included)is not bool:
  raise ValueError('GM states whether current sheet already includes this running bonus')
 if not running_bonus_included:result['high_jump']+=1
 return result

def short_high_jump(c,height,base_height):
 if c.kind=='trainer' and base_height==0 and height<1:
  source(c);return True
 return False


EDGE_NAMES={"edge/파워-부스트":("파워 부스트","Power Boost"),"edge/수영-선수":("수영 선수","Swimmer"),"edge/여행자":("여행자","Traveler"),"edge/곡예사":("곡예사","Acrobat"),"edge/패기":("패기","Dynamism")}

def has_edge(c,uid):
 if c.kind!='trainer':return False
 names=(uid,)+EDGE_NAMES[uid]
 count=sum(value in names for value in c.spec.get('edges',[]))
 if count>1:raise ValueError('duplicate acquired capability edge')
 if count and c.r._selected_rule(uid)!=uid:raise ValueError('selected capability edge variant needs its own policy')
 if count and uid=='edge/수영-선수' and not __import__('hobbyist').skill_waived(c,uid) and max(S.rank(c.r,c,'육상')[2],S.rank(c.r,c,'생존')[2])<3:
  raise ValueError('Swimmer requires Novice Athletics or Survival')
 return bool(count)

def traveler_choices(c):
 owned=has_edge(c,'edge/여행자');records=c.spec.get('edge_choices',{})
 aliases=('edge/여행자','여행자','Traveler')
 chosen=[value for key,value in records.items() if key in aliases]
 if not owned:
  if chosen:raise ValueError('Traveler choice requires acquired edge')
  return ()
 if len(chosen)!=1 or not isinstance(chosen[0],(list,tuple)):
  raise ValueError('Traveler needs explicit substitutions: jump, land and/or power; empty means no substitution')
 values=tuple(chosen[0])
 if len(set(values))!=len(values) or any(value not in ('jump','land','power') for value in values):
  raise ValueError('unknown or repeated Traveler substitution')
 return values

def swimming(c,land,*,base_swim=None):
 result=M.ratio(land,2) if base_swim is None else base_swim
 if not has_edge(c,'edge/수영-선수'):return result
 return LIMITS.add_sources(result,[{'id':'swimmer','source':'edge/수영-선수','value':2}])['value']

def breath_grace(c,medium,*,engine=None):
 base=60 if medium!='water' or not has_edge(c,'edge/수영-선수') else 60*max(__import__('hobbyist').direct_rank(c,'edge/수영-선수','육상'),__import__('hobbyist').direct_rank(c,'edge/수영-선수','생존'))
 base=max(base,__import__('survivalist_class').breath_seconds(c,medium,engine))
 return base+c.spec.get('_respiration',{}).get('style_extension',0)

def derived_power(c):
 source(c)
 choice=c.spec.get('power_policy')
 if choice not in (CORE_POWER_POLICY,'ch02:123','ch02:208'):
  raise ValueError('trainer Power needs explicit source choice core1.05:p16+p18, ch02:123 or ch02:208')
 # Official core1.05 p56 restores the omitted Athletics term in the Korean
 # Traveler translation; source repair recorded in trainer-capability-source-review.json.
 athletics=S.effective_rank(c.r,c,'생존' if 'power' in traveler_choices(c) else '육상');combat=S.effective_rank(c.r,c,'전투')
 return 4+int(athletics>=(4 if choice=='ch02:123' else 3))+int(combat>=4)


def jump_bonuses(c,base):
 """Apply owned Acrobat once to explicit base values; current sheets bypass it."""
 result=dict(base)
 if has_edge(c,'edge/곡예사'):
  if not __import__('hobbyist').skill_waived(c,'edge/곡예사') and S.rank(c.r,c,'곡예')[2]<3:raise ValueError('Acrobat requires an acquired Novice Acrobatics skill')
  for key in ('high_jump','long_jump'):
   if key in result:result[key]=LIMITS.add_sources(result[key],[{'id':'acrobat:'+key,'source':'edge/곡예사','value':1}])['value']
 return result


def initiative_bonus(c):
 """Dynamism is a live Guile-rank contribution, separate from stored bonuses."""
 if not has_edge(c,'edge/패기'):return 0
 if not __import__('hobbyist').skill_waived(c,'edge/패기') and S.rank(c.r,c,'교활')[2]<3:raise ValueError('Dynamism requires an acquired Novice Guile skill')
 basis=c.spec.get('initiative_basis')
 if basis not in ('base','current'):raise ValueError('Dynamism initiative needs explicit base or current bonus basis')
 return __import__('hobbyist').direct_rank(c,'edge/패기','교활') if basis=='base' else 0
