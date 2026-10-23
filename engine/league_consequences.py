"""The result of a League loss creates no automatic property/life/world loss.
Actual lethal injury events remain governed by life.py, never erased by a tag.
"""
from copy import deepcopy
SOURCE='ch06-gameplay/플레이어를-위한-팁/패배를-받아들일-준비를-하세요'
def source(e):
 if e.r._selected_rule(SOURCE)!=SOURCE:raise ValueError('selected League defeat source requires its own policy')
def begin(e,actors,bindings):
 source(e)
 rows=getattr(e,'_league_outcomes',{})
 sequence=len(rows)+1;key='league:'+str(sequence)
 if key in rows:raise ValueError('League outcome identity collision')
 row={'id':key,'sequence':sequence,'source':SOURCE,'status':'active','actors':dict(actors),'bindings':tuple(bindings),'started_at':e.elapsed_seconds}
 if not hasattr(e,'_league_outcomes'):e._league_outcomes={}
 e._league_outcomes[key]=row
 return key
def preflight_end(e,key):
 source(e);row=e._league_outcomes[key]
 if row['source']!=SOURCE or row['status']!='active':raise ValueError('actual unclosed League receipt required')
 return row
def finish(e,key):
 row=preflight_end(e,key)
 row.update(status='awaiting_ruling',ended_at=e.elapsed_seconds,observed={k:{'hp':a.hp,'dead':a.dead,'fainted':a.fainted} for k,a in row['actors'].items()})
 return key
def result(e,actor,*,encounter_id,winner,reason):
 source(e)
 if not isinstance(reason,str) or not reason.strip():raise ValueError('GM actual League result reason required')
 row=getattr(e,'_league_outcomes',{}).get(encounter_id)
 if not row or row.get('source')!=SOURCE or row['status']!='awaiting_ruling':raise ValueError('actual finished, unconsumed League receipt required')
 trainers={player:row['actors'][key] for player,role,key in row['bindings'] if role=='trainer'}
 if actor not in trainers.values() or winner not in trainers:raise ValueError('actual participating trainer and winning player required')
 row.update(status='settled',winner=winner,reason=reason,losers=[p for p in trainers if p!=winner])
 # This is an outcome record, not a call to deduct money, kill/revive, replace
 # a character, or end a campaign. Independent explicit wager payouts are separate.
 return {'encounter_id':encounter_id,'winner':winner,'losers':list(row['losers']),'automatic_loss':None,'status':'settled'}
