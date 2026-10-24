"""Q19: actual acquired family alternatives and real HB Mystic befriend."""
from copy import deepcopy
from pathlib import Path
import json
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
from engine import Rules,Engine
import elemental_connection as E
import items as ITEMS
from native_scenario_fixture import assert_rejected_unchanged
import test_category3_elemental_connection as BASE
import world_entities as WORLD


class ElementalMysticQ19SourceRevisionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.r=Rules(str(ROOT),ruleset='all')
    setUp=BASE.ElementalTests.setUp
    actor=BASE.ElementalTests.actor

    def own(self,edges,types):
        self.a.spec.update(edges=list(edges),edge_choices=deepcopy(types))

    def choice(self,elemental=None,mystic=None,actor=None):
        actor=self.a if actor is None else actor
        pending=E.family_source_choices(self.e,actor)
        return {'value':(elemental or '')+'|'+(mystic or ''),
            'reason':'actual acquired alternative definitions explicitly selected',
            'scope':pending['decision_scope']}

    def select(self,elemental=None,mystic=None):
        return E.observe_family_source(self.e,self.a,self.choice(elemental,mystic))

    def start(self):
        self.p.spec.update(wild=True,disposition='중립')
        self.e.start_round(self.e.everyone);self.e.start_of_turn(self.a,initiative_count=20)

    def roll(self,skill='매력',target=None,faces=4):
        return self.e.skill_roll(self.a,skill,skill_target=self.p if target is None else target,fixed=[3]*faces)

    def test_actual_ordinary_csv55_single_type_and_csv61_native_mystic_activity(self):
        self.own([E.CSV_SOURCE],{E.CSV_SOURCE:'불꽃'});ITEMS.register_feats(self.e,self.a)
        for skill in E.SKILLS:self.assertEqual(self.roll(skill).total,14)
        self.assertEqual(E.choices(self.e,self.a,E.CSV_SOURCE),('불꽃',))
        self.assertNotIn(E.SOURCE_OBSERVATION,self.a.spec)
        self.a.spec['edges'].append(E.CSV_SOURCE)
        assert_rejected_unchanged(self.e,lambda:self.roll(),reason_pattern='one acquired type')
        self.own([E.CSV_MYSTIC],{});ITEMS.register_feats(self.e,self.a)
        self.start();result=self.e.pokemon_activity(self.a,'befriend',target=self.p,use_mystic_senses=True,fixed=[3]*4)
        self.assertEqual((result['skill'],result['check'].total,result['disposition']),('직감',12,'우호적'))
        self.assertEqual(E.require_mystic(self.e,self.a),E.CSV_MYSTIC)
        self.assertEqual(self.a.budget['standard'],0)

    def test_actual_hb_pair_selection_preserves_owned_alternatives_and_reaches_paid_befriend(self):
        self.own([E.SOURCE,E.HOMEBREW,E.MYSTIC,E.HB_MYSTIC],{E.SOURCE:'물',E.HOMEBREW:'불꽃'})
        owned=deepcopy((self.a.spec['edges'],self.a.spec['edge_choices']))
        self.start()
        assert_rejected_unchanged(self.e,lambda:self.e.skill_roll(self.a,'직감',skill_target=self.p),reason_pattern='family source selection')
        assert_rejected_unchanged(self.e,lambda:self.e.pokemon_activity(self.a,'befriend',target=self.p,use_mystic_senses=True),reason_pattern='family source selection')
        self.assertEqual(self.a.budget['standard'],1)
        self.select(E.HOMEBREW,E.HB_MYSTIC);ITEMS.register_feats(self.e,self.a)
        self.assertEqual((self.a.spec['edges'],self.a.spec['edge_choices']),owned)
        for skill in E.SKILLS:self.assertEqual(self.roll(skill).total,14)
        self.assertEqual(self.roll('육상').total,12)
        self.assertEqual(E.require_mystic(self.e,self.a),E.HB_MYSTIC)
        result=self.e.pokemon_activity(self.a,'befriend',target=self.p,use_mystic_senses=True,fixed=[2,2,3,3])
        self.assertEqual((result['skill'],result['check'].total,result['disposition']),('직감',12,'우호적'))
        self.assertEqual(self.a.budget['standard'],0);self.assertFalse(result['captured'])
        self.assertEqual(self.p.spec['disposition_history'][-1]['check_total'],12)
        self.assertNotIn(E.SOURCE_OBSERVATION,self.a.spec)

    def test_any_active_ordinary_counterpart_forbids_the_whole_other_family_before_payment(self):
        for elemental,mystic in ((E.SOURCE,E.HB_MYSTIC),(E.CSV_SOURCE,E.HB_MYSTIC),
                (E.HOMEBREW,E.MYSTIC),(E.HOMEBREW,E.CSV_MYSTIC)):
            with self.subTest(elemental=elemental,mystic=mystic):
                self.setUp();self.own([elemental,mystic],{elemental:'불꽃'});self.start()
                assert_rejected_unchanged(self.e,lambda:ITEMS.register_feats(self.e,self.a),reason_pattern='mutually exclusive')
                assert_rejected_unchanged(self.e,lambda:self.e.skill_roll(self.a,'직감',skill_target=self.p),reason_pattern='mutually exclusive')
                assert_rejected_unchanged(self.e,lambda:self.e.pokemon_activity(self.a,'befriend',target=self.p,use_mystic_senses=True),reason_pattern='mutually exclusive')
                choice=self.choice(elemental,mystic)
                assert_rejected_unchanged(self.e,lambda:E.observe_family_source(self.e,self.a,choice),reason_pattern='mutually exclusive')
                self.assertEqual(self.a.budget['standard'],1)

    def test_actual_actor_types_source_and_owned_set_bind_choice_without_free_acquisition_or_double_bonus(self):
        self.own([E.SOURCE,E.SOURCE,E.HOMEBREW],{E.SOURCE:['불꽃','비행'],E.HOMEBREW:'불꽃'})
        choice=self.choice(E.HOMEBREW)
        other=self.actor('other acquired alternative trainer');other.pos=(7,4)
        other.spec.update(edges=deepcopy(self.a.spec['edges']),edge_choices=deepcopy(self.a.spec['edge_choices']))
        self.e.everyone.append(other)
        assert_rejected_unchanged(self.e,lambda:E.observe_family_source(self.e,other,choice),reason_pattern='scope changed')
        bad=self.choice(E.CSV_SOURCE)
        assert_rejected_unchanged(self.e,lambda:E.observe_family_source(self.e,self.a,bad),reason_pattern='invalid policy input')
        E.observe_family_source(self.e,self.a,choice)
        self.assertEqual(self.roll().total,14)
        self.select(E.SOURCE)
        self.assertEqual(self.roll().total,16)
        # Q1 remains the same native-only observation and overlap law.
        q1=E.source_choices(self.e,self.a)
        self.e.gm.observe_elemental_connection_source(self.a,{'value':'kr_branch_once_per_check',
            'reason':'actual native Q1 overlap interpretation','scope':q1['decision_scope']})
        native_history=deepcopy(self.a.spec[E.SOURCE_OBSERVATION]);self.assertEqual(self.roll().total,14)
        family_history=deepcopy(self.a.spec[E.FAMILY_OBSERVATION])
        self.a.spec['edge_choices'][E.HOMEBREW]='물'
        assert_rejected_unchanged(self.e,lambda:self.e.skill_roll(self.a,'매력',skill_target=self.p),reason_pattern='scope changed')
        self.assertEqual(self.a.spec[E.FAMILY_OBSERVATION],family_history)
        self.assertEqual(self.a.spec[E.SOURCE_OBSERVATION],native_history)
        self.select(E.HOMEBREW);self.assertEqual(self.roll().total,12)
        old=self.r.selection.excluded.get(E.HOMEBREW);self.r.selection.excluded[E.HOMEBREW]='exclude_units'
        try:
            assert_rejected_unchanged(self.e,lambda:self.e.skill_roll(self.a,'매력',skill_target=self.p),reason_pattern='Excluded rule')
        finally:
            if old is None:self.r.selection.excluded.pop(E.HOMEBREW,None)
            else:self.r.selection.excluded[E.HOMEBREW]=old

    def test_current_family_selection_and_declared_seven_survive_gm_fresh_rules_and_inactive_history(self):
        self.own([E.SOURCE,E.HOMEBREW,E.HB_MYSTIC],{E.SOURCE:'물',E.HOMEBREW:'불꽃'})
        self.a.spec['skills']['직감']=7
        retained=self.select(E.HOMEBREW,E.HB_MYSTIC)
        self.assertEqual(self.roll('직감',faces=7).total,23)
        original=deepcopy((self.a.spec['edges'],self.a.spec['edge_choices']))
        self.e.gm.snapshot('q19-current-family');self.e.gm.restore('q19-current-family')
        self.e=Engine.import_state(Rules(str(ROOT),ruleset='all'),json.loads(json.dumps(self.e.export_state(),ensure_ascii=False)))
        index=WORLD.actor_index(self.e);self.a,self.p,self.other=[index[c.entity_id] for c in (self.a,self.p,self.other)]
        self.assertEqual(self.a.spec[E.FAMILY_OBSERVATION],retained)
        self.assertEqual((self.a.spec['edges'],self.a.spec['edge_choices']),original)
        self.assertEqual(self.roll('직감',faces=7).total,23)
        self.start();result=self.e.pokemon_activity(self.a,'befriend',target=self.p,use_mystic_senses=True,fixed=[2]*7)
        self.assertEqual((result['skill'],result['check'].total),('직감',16))
        self.assertEqual(self.a.budget['standard'],0)
        self.a.spec.update(edges=[],edge_choices={})
        self.assertEqual(self.roll('직감',faces=7).total,21)
        self.assertEqual(self.a.spec[E.FAMILY_OBSERVATION],retained)
        self.e=Engine.import_state(Rules(str(ROOT),ruleset='all'),json.loads(json.dumps(self.e.export_state(),ensure_ascii=False)))
        self.a=WORLD.actor_index(self.e)[self.a.entity_id]
        self.assertEqual(self.a.spec[E.FAMILY_OBSERVATION],retained)
        assert_rejected_unchanged(self.e,lambda:E.family_source_choices(self.e,self.a),reason_pattern='actual acquired')


if __name__=='__main__':unittest.main()
