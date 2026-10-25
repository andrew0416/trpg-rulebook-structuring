"""AST/source and stdlib scalar regressions; deliberately no game module imports."""
import ast
import csv
from fractions import Fraction
import math
from pathlib import Path
import re
from types import SimpleNamespace
import unittest

import audit_common_arithmetic_consumers as AUDIT

ROOT=Path(__file__).resolve().parents[1]


def _tree(file):return ast.parse((ROOT/file).read_text(encoding='utf-8-sig'))
def _shape(node):return ast.dump(node,include_attributes=False)
def _contains(file,function,expression):
    expected=_shape(ast.parse(expression,mode='eval').body)
    functions=[node for node in ast.walk(_tree(file)) if isinstance(node,ast.FunctionDef) and node.name==function]
    return sum(_shape(node)==expected for owner in functions for node in ast.walk(owner))
def _eval(expression,**values):
    return eval(compile(ast.parse(expression,mode='eval'),'<synthetic scalar>','eval'),{'__builtins__':{}},values)
def _ceil(n,d):return -((-n)//d)


class ArithmeticSourceBoundaryTests(unittest.TestCase):
    def test_shared_math_delegations_preserve_signed_integer_operators(self):
        self.assertEqual(_contains('engine/arithmetic_policy.py','ratio','floor(A.exact(numerator) / A.exact(denominator))'),1)
        self.assertEqual(_contains('engine/arithmetic_policy.py','floor','A.round_down(value)'),1)
        self.assertEqual(_contains('engine/arithmetic_policy.py','ceil_ratio','A.round_up(A.exact(numerator) / A.exact(denominator))'),1)
        values=list(range(-31,32))+[-(2**256+3),2**256+1]
        for numerator in values:
            for denominator in (-13,-5,-2,-1,1,2,5,13):
                exact=Fraction(numerator,denominator)
                self.assertEqual(numerator//denominator,math.floor(exact))
                self.assertEqual(-((-numerator)//denominator),math.ceil(exact))

    def test_noninteger_dispositions_require_exact_owner_and_expression(self):
        for (file,function,kind,expression),answer in AUDIT.REVIEWED_CONTEXTS.items():
            with self.subTest(file=file,function=function,expression=expression):
                self.assertEqual(AUDIT.classify(file,function,kind,expression),answer)
                for f,fn,expr in ((file,function+'.unreviewed',expression),
                                  ('new_consumer.py',function,expression),
                                  (file,function,expression+' + 0')):
                    self.assertEqual(AUDIT.classify(f,fn,kind,expr)[0],'needs_review')

    def test_new_path_reviews_do_not_allow_numeric_neighbors(self):
        owners=(('acquired_feature_projections.py','_load'),('chef_cooking.py','definitions'),
                ('mentor_csv.py','_catalog'),('move_state.py','ability_registration'),
                ('source_scoped_ability_grants.py','_load'),('state_codec.py','_corpus_paths'),
                ('state_codec.py','rules_fingerprint'),('survivalist_class.py','definitions'))
        for file,function in owners:
            for expression in AUDIT.REVIEWED_PATHS[(file,function)]:
                with self.subTest(file=file,function=function,expression=expression):
                    self.assertEqual(AUDIT.classify(file,function,'division',expression)[0],'filesystem_or_parser')
                    self.assertEqual(AUDIT.classify(file,function,'division','root / 2')[0],'needs_review')
                    self.assertEqual(AUDIT.classify(file,function+'.other','division',expression)[0],'needs_review')

    def test_color_d12_indices_match_every_source_table_cell(self):
        with (ROOT/'input/db/abilities.csv').open(encoding='utf-8-sig',newline='') as handle:rows=list(csv.reader(handle))
        source=rows[227];self.assertEqual(source[0],'색채이론')
        line=source[2].splitlines()[1]
        table={int(face):color.rstrip('.') for face,color in re.findall(r'(\d+)=(\S+)',line)}
        names=('빨강','주황','노랑','초록','파랑','보라')
        expected={roll:names[(roll-1)//2] if roll%2 else names[roll//2-1]+'-'+names[(roll//2)%6]
                  for roll in range(1,13)}
        self.assertEqual(table,expected)
        assignment=next(n for n in _tree('engine/ability_native_actions.py').body
                        if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='COLOR_NAMES' for t in n.targets))
        self.assertEqual(ast.literal_eval(assignment.value),names)
        self.assertEqual(_contains('engine/ability_native_actions.py','_color_payload','(roll - 1) // 2'),1)
        self.assertEqual(_contains('engine/ability_native_actions.py','_color_payload','roll // 2'),1)

    def test_new_path_dispositions_keep_their_native_path_bindings(self):
        bindings=(('acquired_feature_projections.py','_load','Path(root)'),
                  ('chef_cooking.py','definitions','Path(rules.root)'),
                  ('mentor_csv.py','_catalog','Path(rules.root)'),
                  ('move_state.py','ability_registration','Path(rules.root)'),
                  ('source_scoped_ability_grants.py','_load','Path(root)'),
                  ('state_codec.py','rules_fingerprint','Path(rules.root)'),
                  ('survivalist_class.py','definitions','Path(rules.root)'))
        for file,function,expression in bindings:
            with self.subTest(file=file):self.assertGreaterEqual(_contains('engine/'+file,function,expression),1)
        self.assertEqual(_contains('engine/state_codec.py','rules_fingerprint','_corpus_paths(root)'),1)

    def test_duelist_ceil_is_a_local_source_exception_not_default_floor(self):
        line=(ROOT/'input/ch04-trainer-classes.md').read_text(encoding='utf-8-sig').splitlines()[731]
        self.assertIn('탄력',line);self.assertIn('절반(올림)',line)
        for function in ('accuracy','evasion'):
            self.assertEqual(_contains('engine/duelist.py',function,'NUMERIC.ceil_ratio(momentum(pokemon),2)'),1)
        for value in range(-21,22):
            self.assertEqual(_ceil(value,2),(value+1)//2)
        self.assertNotEqual(_ceil(3,2),3//2)

    def test_signed_operand_order_is_preserved_for_manual_capture(self):
        expression='M.ratio(-CSV_ITEMS.manual_capture_modifier(self,trainer,target,type_manual_instance_id),5)'
        self.assertEqual(_contains('engine/engine.py','throw_ball',expression),1)
        for value in range(-31,32):self.assertEqual((-value)//5,math.floor(Fraction(-value,5)))
        self.assertNotEqual(math.floor(Fraction(-3,5)),-math.floor(Fraction(3,5)))

    def test_capture_thresholds_are_exact_at_odd_and_large_maxima(self):
        predicates=(('current*4 <= target.base_max_hp',4,1,2),
                    ('current*2 <= target.base_max_hp',2,1,2),
                    ('current*4 <= target.base_max_hp*3',4,3,1))
        witnessed=False
        for expression,denominator,numerator,count in predicates:
            self.assertEqual(_contains('engine/capture_resolution.py','rate',expression),count)
            for maximum in list(range(1,30))+list(range(2**54,2**54+32)):
                boundary=maximum*numerator//denominator
                for current in (max(0,boundary-1),boundary,boundary+1):
                    expected=current<=Fraction(maximum*numerator,denominator)
                    self.assertEqual(_eval(expression,current=current,target=SimpleNamespace(base_max_hp=maximum)),expected)
                    witnessed|=(current<=maximum*numerator/denominator)!=expected
        self.assertTrue(witnessed,'large integer precision witness must exercise the repaired representation')

    def test_extra_turn_half_thresholds_remain_exact_for_signed_large_counts(self):
        line=(ROOT/'input/ch04-trainer-classes.md').read_text(encoding='utf-8-sig').splitlines()[2761]
        self.assertIn('이니셔티브의 절반 이하',line)
        self.assertEqual(_contains('engine/initiative_schedule.py','grant_extra_turn','count*2>initiative'),1)
        self.assertEqual(_contains('engine/initiative_schedule.py','validate_extra_turns',"origin['count']*2>origin['initiative']"),1)
        self.assertEqual(_contains('engine/tumbler.py','burst_offer','answer*2>value.value'),1)
        for initiative in list(range(-20,21))+[2**54+3,2**55+7]:
            for count in (initiative//2-1,initiative//2,initiative//2+1):
                self.assertEqual(_eval('count*2>initiative',count=count,initiative=initiative),count>Fraction(initiative,2))
        initiative=2**54+3;count=initiative//2+1
        self.assertNotEqual(count>initiative/2,count*2>initiative)

    def test_recovery_ceil_is_the_first_complete_integral_clock(self):
        with (ROOT/'input/db/item-data.csv').open(encoding='utf-8-sig',newline='') as handle:rows=list(csv.reader(handle))
        self.assertEqual(rows[177][4],'개선된 인조 근육');self.assertIn('twice as fast',rows[177][7])
        self.assertEqual(_contains('engine/csv_item_capability_contracts.py','injury_recovery_seconds','NUMERIC.ceil_ratio(ordinary_seconds,2)'),1)
        for seconds in list(range(20))+[2**54+1,2**55+3]:
            completed=_ceil(seconds,2)
            self.assertGreaterEqual(2*completed,seconds)
            if completed:self.assertLess(2*(completed-1),seconds)
        seconds=2**54+1
        self.assertNotEqual(math.ceil(seconds/2),_ceil(seconds,2))

    def test_team_ceiling_is_minimum_integral_success_not_a_floor_override(self):
        self.assertEqual(_contains('engine/skill_feature_actions.py','resolve_team','NUMERIC.ceil_ratio(remainder,multipliers[index])'),1)
        for remaining in range(-30,31):
            for multiplier in range(1,7):
                threshold=_ceil(remaining,multiplier)
                self.assertGreaterEqual(threshold*multiplier,remaining)
                self.assertLess((threshold-1)*multiplier,remaining)

    def test_homebrew_endure_uses_negative_final_hp_threshold_not_negated_positive_loss(self):
        with (ROOT/'input/db/moves.csv').open(encoding='utf-8-sig',newline='') as handle:rows=list(csv.reader(handle))
        self.assertEqual(rows[908][0],'버티기 [홈브류]')
        self.assertIn('[-25%] 이하',rows[908][7])
        self.assertEqual(rows[477][0],'버티기');self.assertNotIn('25%',rows[477][7])
        self.assertEqual(_contains('engine/endure.py','replace_hp',"receipt['source']==SOURCES[1] and proposed*4<=-target.base_max_hp"),1)
        self.assertEqual(_contains('engine/endure.py','replace_hp','target.base_max_hp//4'),0)
        for maximum in list(range(1,100))+[2**128+3,2**256+1]:
            threshold=math.floor(Fraction(-maximum,4))
            for proposed in (threshold-1,threshold,threshold+1,0):
                self.assertEqual(proposed*4<=-maximum,proposed<=threshold)
        self.assertFalse(-20*4<=-83);self.assertTrue(-21*4<=-83)
        self.assertNotEqual(-(83//4),math.floor(Fraction(-83,4)))


if __name__=='__main__':unittest.main()
