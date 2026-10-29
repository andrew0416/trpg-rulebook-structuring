"""Inventory explicit scalar boundaries; no claim to prove every dynamic extension."""
import ast,json,hashlib
from pathlib import Path
from collections import Counter
ROOT=Path(__file__).resolve().parents[1]


# Exact reviewed path expressions, scoped to their inspected functions. Never
# classify an arbitrary variable named root as a filesystem path.
REVIEWED_PATHS = {
 ('state_codec.py','rules_fingerprint'): ("root/'data/poke-edge-variants.json'", "root/'data/training-source-policies.json'"),
 ('base_stage_abilities.py','definitions'): ("root/'data/base-stage-abilities.json'", "root/policy['source_file']", "root/'output/entities/abilities.json'"),
 ('homebrew_weather.py','policy'): ("root/'data/homebrew-weather-policy.json'", "root/'input/hb-weather.md'"),
 ('poke_edge_variants.py','catalog'): ("root/'data/poke-edge-variants.json'", "root/data['source_file']"),
 ('pokemon_activities.py','_groomer_csv_source'): ("root/'data/training-source-policies.json'", "root/policy['file']"),
 ('source_catalog.py','_document'): ("root / 'data/source-catalog.json'", "root / entry['source_file']", "root / 'input'"),
 ('source_catalog.py','definition'): ("root / entry['source_file']", "root / 'input'"),
 ('source_policy.py','register_sources'): ("root/source['file']", "root/'input'"),
 ('state_codec.py','rules_fingerprint.saved_policy'): ("root/'data'/filename", "root/'data'"),
 ('weather_templates.py','require'): ("root/'input/hb-weather.md'", "root/'data/homebrew-weather-policy.json'"),
}


def classify(file,fn,kind,expr):
 # Narrowly reviewed category2 consumers; new sites still require review.
 if kind=='division' and expr in REVIEWED_PATHS.get((file,fn),()):return 'filesystem_or_parser','Inspected function binds root to pathlib.Path(rules.root); exact file expression, not numeric division.'
 if file=='telekinetic_load.py' and fn=='range_check' and kind=='floor_division' and expr=='min(dx,dy)//2':return 'geometry_or_parser','Integer diagonal-pair count in max(dx,dy)+min(dx,dy)//2; matches ch07-combat:132 alternating 1,2 metre diagonals and Grid.diagonal_cost, not generic rounding.' 
 if kind=='division' and ((file=='actor_templates.py' and fn=='policy' and expr in ('root / "data/category2-encounter-template-policy.json"','root / name')) or (file=='state_codec.py' and fn=='rules_fingerprint' and expr=='root / directory')):return 'filesystem_or_parser','Reviewed pathlib composition; no numeric value.'
 if file=='body_state.py' and fn=='trainer_weight' and kind=='division' and expr=='quantity/Decimal("0.45359237")':return 'physical_unit_conversion','Exact decimal kg/lb measurement conversion for interval comparison; no integer game quantity is produced.'
 if file=='species_metadata.py' and fn=='sex_distribution' and kind=='division' and expr in ('values[0]/scale','values[1]/scale'):return 'catalog_ratio','Source sex fractions/percentages normalized to probabilities, which must remain fractional.'
 if file=='special_entities.py' and fn=='validate_compartments' and kind=='floor_division' and expr=="sum(x['breach_capacity'] for x in rows)*2//3":return 'reviewed_integer_formula','SPOL-062 positive integral breach capacity: floor exactly once after taking two thirds of the summed sections, before adding integral armor contribution.'
 if kind=='division' and ('Path(' in expr or '/ref[' in expr):return 'filesystem_or_parser','Filesystem path composition, not numerical division.'
 if file in ('arithmetic.py','arithmetic_policy.py'):return 'common_implementation','Exact neutral math or PTK numeric policy implementation.'
 if kind=='policy_call':return 'connected_policy','The existing named boundary delegates to arithmetic_policy; pure calculators rely on their source-selecting caller.'
 if file=='rulings.py' and fn=='calc':return 'connected_exact_formula','Formula keeps rational intermediates; its consumer owns integerization.'
 if file.startswith('root_'):return 'model_or_path','Root exact declarative algebra, input validation or filesystem path; no new game integerization.'
 if file in ('passive_event_profiles.py','adjudication_guidance.py','capability_policies.py','skill_context_policy.py','weapon_policy.py'):return 'filesystem_or_parser','Filesystem path or configuration parser, not a numerical result.'
 if file=='downtime.py' and fn=='gain_exp_combatant' and (kind in ('division','floor_division') or 'round(' in expr):return 'unresolved_legacy_policy','N14: proportional level-up HP and nearest rounding have no verified source; preserved, not certified by CORE-005.'
 if file=='builder.py' and fn in ('allocate','allocate_stats','allocate_increment','add_stat_points'):return 'optimizer','Stat allocation strategy score or integer apportionment heuristic; not a rulebook rounding boundary.'
 if file=='custom_species.py':return 'diagnostic','Statistical percentile/report indexing, not gameplay quantization.'
 if file in ('grid.py','jump_actions.py','net_capsule.py'):return 'geometry_or_parser','Exact geometric algorithm / explicit alternating diagonal-count formula; retain its own operator.'
 if file=='movement_actions.py' and kind in ('division','floor_division'):return 'geometry_or_physical_threshold','Alternating grid metric or fractional Levitate height threshold. Physical heights can be fractional; no integer quantity is being produced.'
 if file=='heavy_injury_kernel.py':return 'strict_boundary_formula','Signed exact threshold-crossing formula (2*hp-1)//H, not arbitrary fraction-to-game-integer conversion.'
 if file=='encounter.py':return 'simulation_strategy','AI scoring ratio or simulation configuration parser, not resolution math.'
 if file=='downtime.py' and fn=='<module>':return 'demo','Standalone demo fixture, not native runtime.'
 if kind=='division' and file in ('effects.py','effects_ext.py'):return 'exact_threshold','HP predicate compares against a fractional threshold; no whole-number result is produced.'
 if kind=='int_call':return 'integer_input_or_parser','Integer schema/string parsing/boolean counting; source of numeric values is separately validated. Any non-integer result boundary is recorded by policy_call or an unresolved entry.'
 if kind in ('floor_call','ceil_call','round_call','division','floor_division'):return 'needs_review','Not yet assigned a semantic disposition.'
 return 'exact_intermediate','Neutral exact arithmetic or preserved declared factor, not an integerization boundary.'


def inventory():
 records=[];hashes={}
 for path in sorted((ROOT/'engine').glob('*.py')):
  if path.name.startswith(('test_','demo_')):continue
  text=path.read_text(encoding='utf8');tree=ast.parse(text);hashes[str(path.relative_to(ROOT)).replace('\\','/')]=hashlib.sha256(path.read_bytes()).hexdigest()
  policy_aliases={alias.asname or alias.name for node in ast.walk(tree) if isinstance(node,ast.Import) for alias in node.names if alias.name=='arithmetic_policy'}
  class Visitor(ast.NodeVisitor):
   def __init__(self):self.functions=[]
   def visit_FunctionDef(self,node):
    self.functions.append(node.name);self.generic_visit(node);self.functions.pop()
   visit_AsyncFunctionDef=visit_FunctionDef
   def visit(self,node):
    kind=None
    if isinstance(node,ast.BinOp) and isinstance(node.op,(ast.Div,ast.FloorDiv)):kind='division' if isinstance(node.op,ast.Div) else 'floor_division'
    elif isinstance(node,ast.Call):
     if isinstance(node.func,ast.Name) and node.func.id in ('int','round'):kind=node.func.id+'_call'
     elif isinstance(node.func,ast.Attribute) and isinstance(node.func.value,ast.Name):
      if node.func.value.id in policy_aliases and node.func.attr not in ('validate_source',):kind='policy_call'
      elif node.func.value.id=='math' and node.func.attr in ('floor','ceil'):kind=node.func.attr+'_call'
    if kind:
     fn='.'.join(self.functions) or '<module>';expr=ast.get_source_segment(text,node);status,reason=classify(path.name,fn,kind,expr)
     records.append(dict(file=str(path.relative_to(ROOT)).replace('\\','/'),line=node.lineno,function=fn,kind=kind,expression=expr,status=status,reason=reason))
    return super().visit(node)
  Visitor().visit(tree)
 return records,hashes


def main():
 records,hashes=inventory()
 report={'scope':'Current engine explicit division, int/floor/ceil/round and arithmetic_policy call sites; effect rate inventory reviewed separately. AST inventory is a bounded audit, not proof about arbitrary future GM code.',
 'fixed_denominator':352,'fixed_register_modified':False,
 'generic_math':'engine/arithmetic.py: exact decimal/rational expression evaluation; floor and ceil as explicit operators; no PTK authority.',
 'rulebook_policy':'engine/arithmetic_policy.py: CORE-005 floor at caller-established boundaries; CORE-006 typed same-base positive increases; use-time selected-source validation.',
 'existing_root_algebra':'root_resolution._compose already implements declared exact add/product. It remains a separate model algebra; numeric game policy does not duplicate source arbitration.',
 'counts':dict(Counter(r['status'] for r in records)),'sites':records,'engine_input_hashes':hashes,
 'active_percentage_consumers':[
  {'consumer':'Combatant.staged / M.stage_stat','policy':'Each positive CS contributes +1/5 to the original combat stat; sum before one final floor. Negative stages use the separately stated -1/10 table; GM table overrides remain explicit factors.','source':'ch07:227-257; common-numeric-semantics N05'},
  {'consumer':'movement_actions.distance_budget and Engine.approach','policy':'Sprint is one +50% increase at its movement-budget stage. Existing ch06_once/ch07_turn duration policy remains independent.','source':'ch06:139 / maneuver/질주'},
  {'consumer':'food_effects.baby_xp','policy':'Baby Food boosts the actual experience award by +20%; separate from Encounter significance and challenge factors.','source':'item/이유식'},
  {'consumer':'effects_ext.multiplier_hook','policy':'Current reviewed move data uses Solar Blade weather factor0.5. This is a separately named reduction, never percentage-increase pooling. Unknown future stacked multipliers need a source-specific composition policy.','source':'data/moves-reviewed.json'},
  {'consumer':'reviewed resistance berry item effects','policy':'18 factor0.5 records are reductions; actual native food resistance processing preserves its specific resistance policy and does not add to increase rates.','source':'data/items-reviewed.json'},
  {'consumer':'downtime.award_exp','policy':'Significance and challenge are independent sourced multiplication factors before one division/recipient floor.','source':'ch11:1251-1267'}],
 'unresolved_source_semantics':[
  {'id':'negative_operand','state':'unresolved_source_operand','detail':'floor(-H/2) differs from -floor(H/2). Negative floor as an operator is exact, but no global clause chooses the operand order of every negative HP setting. Preserve existing self_hp_set magnitude boundary, not whole-source certification.'},
  {'id':'injury_rounding_stage','state':'unresolved_source_boundary','detail':'H59/I3: per-injury floor gives44 versus final remaining-cap floor41. Existing per-injury boundary preserved. Generic CORE-006 positive-increase policy cannot settle decreases.'},
  {'id':'levelup_hp_policy','state':'unresolved_legacy_policy','detail':'gain_exp_combatant preserves proportional HP via nearest round without verified source. Kept visible; not treated as a sourced nearest-round exception.'},
  {'id':'evasion_translation','state':'provisional_local_source_adoption','detail':'PTK line119 says nearest; combat/stat-per-five and PTU explicitly favor floor. Existing adopted floor retained, not presented as internally consistent translation.'},
  {'id':'speed_half_translation','state':'provisional_local_source_adoption','detail':'PTU explicitly floors signed Speed CS/2; PTK omits the operator. Existing signed //2 semantics retained through common ratio.'},
  {'id':'contest_xp_operand','state':'unresolved_source_operand','detail':'Explicit ceil half-count operator exists, but count identity/example conflict remains outside common encounter XP.'}],
 'whole_source_semantics_complete':False,
 'unclassified_sites':[r for r in records if r['status']=='needs_review']}
 out=ROOT/'output/common-arithmetic-consumer-inventory.json';out.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
 print(json.dumps({'counts':report['counts'],'unclassified_sites':report['unclassified_sites'],'report':str(out)},ensure_ascii=False))
 return bool(report['unclassified_sites'])
if __name__=='__main__':raise SystemExit(main())
