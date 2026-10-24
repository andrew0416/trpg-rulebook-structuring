"""Core308 communication contract; the existing communication owner executes it.

CLASS is the actual Core193 producer that references this capability. The old
Korean capability identity and its historical noncumulative policy stay intact.
"""
from copy import deepcopy
from pathlib import Path
import json
import telepathy as T, perception_communicate as M
SOURCE='class/텔레파시능력자'

def policy(rules):
 value=json.loads((Path(rules.root)/'data/telepathy-core-policy.json').read_text(encoding='utf8'))
 __import__('source_context').verified_source(rules,value['source'],label='Core Telepath')
 if rules._selected_rule(SOURCE)!=SOURCE:raise ValueError('selected exact Core Telepath source required')
 return value

def prepare(e,a,t,value,operation,thought):
 if M._body(policy(e.r)['declaration'])!=M._body(value):raise ValueError('Core Telepath retains its selected printed contract')
 if not T.owns(a):raise ValueError('actual Telepathy Capability required')
 if operation=='read':
  if thought is not None:raise ValueError('reading cannot invent thought content')
 elif operation=='send':
  __import__('crafting_recipes')._text(thought)
  if a.kind=='pokemon' and not T.owns(t):raise ValueError('Pokemon projection requires a Telepathy recipient')
  if t.kind not in ('trainer','pokemon'):raise ValueError('actual Trainer or Pokemon recipient required')
 else:raise ValueError('Core Telepath supports actual reading and projection')

def read_block(e,t,operation):return T.read_block(e,t,operation)
def deliver(e,a,t,thought,operation):return dict(T.deliver(e,a,t,thought,operation),source=SOURCE)
def attempt(e,a,t,operation,unwilling):
 row=M._state(e)['permissions'].get(M._pair(SOURCE,a.entity_id,t.entity_id))
 return dict(T.attempt(e,a,t,operation,not (row is not None and row['allowed'])),source=SOURCE)
def validate_result(e,result):return T.validate_result(e,result,source=SOURCE,cumulative=True)
def retry_modifier(e,failures,penalty):return penalty['modifier']*sum(e.elapsed_seconds<r['at']+penalty['seconds'] for r in failures)
def read(e,a,t,*,request_id,roll_options=None):return M.send(e,a,t,policy(e.r)['declaration'],None,request_id=request_id,roll_options=roll_options,operation='read')
def project(e,a,recipients,thought,*,request_id,roll_options=None):return M.send_many(e,a,recipients,policy(e.r)['declaration'],thought,request_id=request_id,maximum=T.projection_maximum(a),roll_options=roll_options)
def awareness(e,a,t,aware,*,reason):return M.observe_relation(e,a,t,'telepathy_awareness',SOURCE,aware,reason=reason)
