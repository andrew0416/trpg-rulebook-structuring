"""Catalog-wide field inventory; syntactic reads are not semantic certification."""
from pathlib import Path
from collections import Counter,defaultdict
import ast,inspect,json,sys,textwrap,hashlib
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'engine'))
from engine import Rules
import effects as FX,effects_ext as EXT,effect_contracts as C,effect_lifetimes as L
EXT.install()
r=Rules(ROOT);records=[];errors=[];legacy=[]
def walk(value,source,path):
 if isinstance(value,dict):
  if isinstance(value.get('type'),str):records.append(dict(source=source,path=path,effect=value))
  for key,child in value.items():
   if isinstance(child,(dict,list)):walk(child,source,path+'.'+str(key))
 elif isinstance(value,list):
  for i,child in enumerate(value):walk(child,source,path+'['+str(i)+']')
for uid,unit in r.units.items():walk((unit.get('mech') or {}).get('data',{}),uid,'unit.mech.data')
for uid in r.moves:
 try:
  mm,confidence=r.move_mech(uid);walk(mm.get('effects_exec',[]),uid,'runtime.move.effects_exec')
  if set(mm)-{'effects_exec'}:legacy.append(dict(source=uid,fields=sorted(set(mm)-{'effects_exec'}),confidence=confidence))
 except (ValueError,KeyError) as ex:errors.append(dict(source=uid,error=str(ex)))
for name,effects in r.ability_effects.items():walk(effects,'ability/'+name,'runtime.ability.effects')
for uid in set(r.items_mech)|set(r.items_llm)|set(r.items_reviewed):
 if uid.startswith('$'):continue
 try:
  effects,header=r.item_effects(uid);walk(effects,header.get('id',uid),'runtime.item.effects')
 except (ValueError,KeyError) as ex:errors.append(dict(source=uid,error=str(ex)))
for uid in set(r.feats_mech)|set(r.feats_llm)|set(r.feats_reviewed)|set(r.edges_llm)|set(r.edges_reviewed):
 if uid.startswith('$'):continue
 try:
  effects,header=r.feat_effects(uid);walk(effects,header.get('id',uid),'runtime.feature.effects')
 except (ValueError,KeyError) as ex:errors.append(dict(source=uid,error=str(ex)))
fields=defaultdict(Counter);sources=defaultdict(set);controls=[]
for row in records:
 kind=row['effect']['type'];fields[kind].update(row['effect'].keys());sources[kind].add(row['source'])
 if set(row['effect']) & C.CONTROL:controls.append(row)
handlers={}
for kind,fn in FX.HANDLERS.items():
 try:
  tree=ast.parse(textwrap.dedent(inspect.getsource(fn)));reads=set()
  for node in ast.walk(tree):
   if isinstance(node,ast.Call) and isinstance(node.func,ast.Attribute) and isinstance(node.func.value,ast.Name) and node.func.value.id=='e' and node.args and isinstance(node.args[0],ast.Constant):reads.add(str(node.args[0].value))
   if isinstance(node,ast.Subscript) and isinstance(node.value,ast.Name) and node.value.id=='e' and isinstance(node.slice,ast.Constant):reads.add(str(node.slice.value))
  handlers[kind]=dict(callable=fn.__module__+'.'+fn.__name__,file=str(Path(inspect.getsourcefile(fn)).relative_to(ROOT)).replace('\\','/'),line=inspect.getsourcelines(fn)[1],syntactic_reads=sorted(reads),payload_schema=sorted(C.SCHEMAS[kind]) if kind in C.SCHEMAS else None,claim='syntax inventory only; semantic/native source certification is separate')
 except (OSError,TypeError) as ex:handlers[kind]={'error':str(ex)}
report=dict(schema='native-effect-contract-inventory-v1',scope='All nested typed records in selected rule units plus actual runtime move/ability/item/feature streams; duplicate representations retained and path-labelled.',record_count=len(records),types=len(fields),handler_count=len(handlers),control_record_count=len(controls),fields={k:dict(v) for k,v in sorted(fields.items())},sources={k:sorted(v) for k,v in sorted(sources.items())},handlers=handlers,control_records=controls,legacy_move_projections=legacy,selection_errors=errors,supported_lifetime_consumers=sorted(L.KINDS),explicit_control_policy={k:('source adapter required; unsupported is explicit' if k in ('while','repeat','scope','when','at','optional','trigger') else 'explicit dispatcher or native-consumer policy') for k in sorted(C.CONTROL)},limitations=['This inventory is not a percentage of rule implementation. Handler registration and syntactic field reads do not certify semantic support.','Payload types without declared schemas still require consumer-by-consumer audit; note is retained but some source notes may contain mechanics.','Full outer Engine producer continuation certification is separate from effect-batch suffix continuation.','Continuous/repeated rules without actual state/event producers are blocked before native move/item cost; no permanent effect or universal text parser is inferred.','Passive registry and legacy hand-authored projections require source-specific condition/composition review.'])
report['code_sha256']={name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in ['engine/effects.py','engine/effects_ext.py','engine/effect_contracts.py','engine/effect_lifetimes.py','engine/combat_timing.py','engine/engine.py','tools/test_upper_effect_contracts.py']}
out=ROOT/'output/upper-effect-contract-inventory.json';out.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(dict(records=len(records),types=len(fields),handlers=len(handlers),controlled_records=len(controls),selection_errors=len(errors),output=str(out)),ensure_ascii=False))
