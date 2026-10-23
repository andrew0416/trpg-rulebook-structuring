"""Actual subject binding for native checks; reference identity survives retries."""
def validate(e,target):
 if target is not None and (getattr(target,'r',None) is not e.r or getattr(target,'kind',None) not in ('trainer','pokemon')):
  raise ValueError('skill target must be an actual actor in this rule context')
 return target

def bind(e,options,target):
 validate(e,target)
 out=dict(options or {})
 if out.get('skill_target') is not None and out['skill_target'] is not target:
  raise ValueError('skill target differs from actual native target')
 out['skill_target']=target
 return out
