"""PTK source context and table authority, attached to actual native reads.

This records provenance; it never admits sources or executes external prose.
PTK may add/change/delete PTU rules. PTU references below explain omissions,
not an automatic replacement for an explicit PTK field. The selected profile
and explicit table rulings retain their separate, existing execution paths.
"""
from copy import deepcopy
from contextlib import contextmanager
from contextvars import ContextVar

_READ_SCOPES = ContextVar("source_read_scopes", default=())

@contextmanager
def capture_reads(rules):
 rows=[]
 token=_READ_SCOPES.set(_READ_SCOPES.get()+((rules,rows),))
 try:yield rows
 finally:_READ_SCOPES.reset(token)

from ruleset import ExcludedRuleSelection,UnresolvedRuleSelection

INTRO='ch01-intro/ptk란'
CORE_SCOPE='C3-CORE-003'
TABLE_SCOPE='C3-EX-001'

def _text(value,label):
 if not isinstance(value,str) or not value.strip():raise ValueError('nonempty '+label+' required')
 return value


def add_ptu_explanation(rules,uid,*,reference,explanation,reason):
 """Associate a PTU explanation with one selected ID; never install mechanics."""
 for label,value in [('reference',reference),('explanation',explanation),('reason',reason)]:_text(value,label)
 if rules._selected_rule(INTRO)!=INTRO:raise ValueError('selected PTK source-context statement required')
 selected=rules._selected_rule(uid,supports_versions=True)
 row={'source_role':'PTU_supplemental_explanation','reference':reference,
  'explanation':explanation,'reason':reason,'requested_id':uid,'selected_id':selected,
  'executable':False,'authority_clause':CORE_SCOPE}
 refs=rules.__dict__.setdefault('_ptu_explanations',{})
 existing=refs.setdefault(selected,[])
 if row in existing:raise ValueError('same PTU explanation already recorded')
 existing.append(row)
 return deepcopy(row)


def _base(rules,uid):
 selection=rules.select_source_definition(uid,supports_versions=True)
 selected=selection['selected_id']
 return {'selected_id':selected,'selected_source':selection['source'],
  'profile':rules.ruleset.name,'profile_is_source_authority':False,
  'unit_version':rules.ruleset.unit_versions.get(selected),
  'ptu_supplemental_explanations':deepcopy(getattr(rules,'_ptu_explanations',{}).get(selected,[])),
  'automatic_edition_precedence':False,'source_context_clause':CORE_SCOPE,
  'table_authority_clause':TABLE_SCOPE,'whole_engine_certified':False}


def _save(rules,key,record):
 # Latest record per actual consumer, not an unbounded gameplay log or new UI.
 rules.__dict__.setdefault('_source_context_reads',{})[key]=deepcopy(record)
 for owner,rows in _READ_SCOPES.get():
  if owner is rules:rows.append(dict(deepcopy(record),consumer=key))


def mech_read(rules,uid,base,resolved):
 """Parent calls this after selected version + explicit Rulings.apply_mech."""
 record=_base(rules,uid)
 patches=deepcopy(rules.rulings.mech.get(uid,{}))
 record.update({'reader':'mech','original_value':deepcopy(base),'resolved_value':deepcopy(resolved),
  'authority':'table_ruling' if patches else 'selected_source',
  'table_rulings':patches,'ruling_is_source_text':False})
 _save(rules,'mech:'+uid,record)
 return resolved


def formula_read(rules,name,value):
 """Record the actual formula winner without promoting GM data into PTK."""
 # Local import avoids a dependency cycle with the existing formula reader.
 from rulings import FORMULA_DEFAULTS
 source=FORMULA_DEFAULTS.get(name)
 table=deepcopy(rules.rulings.formulas.get(name))
 if source is None:
  if table is None:raise KeyError(name)
  # Explicit table-only formula has no fictitious source-rule identity.
  record={'selected_id':None,'selected_source':None,'profile':rules.ruleset.name,
   'profile_is_source_authority':False,'unit_version':None,
   'ptu_supplemental_explanations':[],'automatic_edition_precedence':False,
   'source_context_clause':CORE_SCOPE,'table_authority_clause':TABLE_SCOPE,'whole_engine_certified':False}
 else:
  try:record=_base(rules,source[0])
  except (ExcludedRuleSelection,UnresolvedRuleSelection) as exc:
   if table is None:raise
   # Existing explicit table formula authority is independent of source
   # applicability. Metadata cannot newly gate that native execution path.
   unit=rules.selection.units.get(source[0])
   record={'selected_id':None,'selected_source':None,'original_rule_id':source[0],
    'original_rule_source':deepcopy(unit['source']) if unit else None,
    'source_selection_status':type(exc).__name__,'profile':rules.ruleset.name,
    'profile_is_source_authority':False,'unit_version':None,
    'ptu_supplemental_explanations':[],'automatic_edition_precedence':False,
    'source_context_clause':CORE_SCOPE,'table_authority_clause':TABLE_SCOPE,'whole_engine_certified':False}
 record.update({'reader':'formula','name':name,'source_field':source[1] if source else None,
  'authority':'table_ruling' if table else 'selected_source',
  'table_ruling':table,'resolved_value':deepcopy(value),'ruling_is_source_text':False})
 _save(rules,'formula:'+name,record)
 return value


def latest(rules,key):
 """A copy of a completed native read; absent reads are not fabricated."""
 records=getattr(rules,'_source_context_reads',{})
 if key not in records:raise KeyError('no actual source-context read: '+key)
 return deepcopy(records[key])


def verified_source(rules, reference, *, label='policy', source_root='input'):
 """Read current source bytes inside the explicit source boundary; never cache freshness.

 This shared boundary checks provenance only, not rule interpretation or choice.
 Consumers retain their own selection, locator and authority checks.
 """
 from pathlib import Path
 from hashlib import sha256
 # Capture a stable absolute spelling once; resolving the source and input
 # boundary below still follows current links on every read.
 root=Path(rules.root).absolute()
 if not isinstance(reference,dict) or not isinstance(reference.get('file'),str) or not isinstance(reference.get('sha256'),str):
  raise ValueError(label+' source file and sha256 required')
 if source_root not in ('input','source-audit'):
  raise ValueError(label+' source boundary must be input or source-audit')
 path=root.joinpath(reference['file']).resolve()
 if not path.is_relative_to(root.joinpath(source_root).resolve()):
  raise ValueError(label+' source must be inside '+source_root)
 content=path.read_bytes()
 if sha256(content).hexdigest()!=reference['sha256']:
  raise ValueError(label+' source changed; review required')
 return content
