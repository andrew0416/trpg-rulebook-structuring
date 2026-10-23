"""Rule-neutral boundary for externally observed optional decisions.

Consumers commit the first private calculation before opening a decision. This
record locks its declaration and result; callback errors only leave it pending.
Rule-specific dice, costs, frequency, targets and timing belong to consumers.
"""
from copy import deepcopy
KEY='observed_resolution'

def locate(records,family,participants,requested=None):
 if requested is not None and (not isinstance(requested,str) or not requested.strip()):raise ValueError('nonempty observed attempt identity required')
 participants=tuple(participants)
 active=[(key,row[KEY]) for key,row in records.items() if KEY in row and row[KEY]['family']==family and row[KEY]['participants']==participants and row[KEY]['state']!='complete']
 if len(active)>1:raise ValueError('more than one unfinished observed attempt for these participants')
 if active:
  key,old=active[0]
  if requested is not None and requested!=key:raise ValueError('finish the existing observed attempt before starting another identity')
  if old['state']=='deciding':raise ValueError('observed decision callback cannot reenter its own attempt')
  return key,old
 if requested is not None:
  old=records.get(requested,{}).get(KEY)
  if old is not None:raise ValueError('observed attempt identity already belongs to a completed or different action')
  return requested,None
 index=len(records)+1;key=family+':'+str(index)
 while key in records:index+=1;key=family+':'+str(index)
 return key,None

def verify(record,declaration):
 if record['declaration']!=declaration:raise ValueError('cannot change an already observed declaration')

def begin(records,key,family,participants,declaration,observation,*,references=()):
 if KEY in records.get(key,{}):raise ValueError('first observation already exists')
 memo={id(x):x for x in (*participants,*references)}
 record={'family':family,'participants':tuple(participants),'declaration':deepcopy(declaration,memo),'observation':observation,'state':'pending'}
 records.setdefault(key,{})[KEY]=record
 return record

def decide(record,callback,preview):
 if record['state']!='pending':raise ValueError('observed attempt is not awaiting a decision')
 if not callable(callback):raise ValueError('an explicit observed decision callback is required')
 record['state']='deciding'
 try:
  chosen=callback(preview)
  if type(chosen) is not bool:raise ValueError('observed decision must be true or false; original result remains pending')
  return chosen
 finally:record['state']='pending'

def complete(record,result):
 if record['state']!='pending':raise ValueError('observed attempt cannot be completed now')
 record['result']=result;record['state']='complete'
 return result
