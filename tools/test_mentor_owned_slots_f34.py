"""F34: existing owned slot passives follow actual ownership producers."""
from pathlib import Path
from copy import deepcopy
from unittest.mock import patch
import json,sys,unittest

ROOT=Path(__file__).resolve().parents[1]
if not (ROOT/'input').is_dir():ROOT=Path('D:/trpg-rulebook-structuring/ptk-structure-experiment')
sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
import test_category2_move_quota_safety as QUOTA
import test_core_first_owned_species as FIRST
import test_foundation_egg_creation as EGG
from engine import Rules
from builder import build_trainer,build_pokemon
import items as ITEMS,move_state as MOVES,pokemon_party as PARTY
import state_grants as GRANTS,state_codec as CODEC,world_entities as WORLD

FEATURES=(MOVES.GUIDANCE,MOVES.LIFELONG,
          'C2CSV/input/db/feats.csv:R107:main','C2CSV/input/db/feats.csv:R110:main')
STATS=dict.fromkeys(('hp','atk','def','spa','spd','spe'),10)
TAUGHT=('화염방사','열풍','10만볼트','냉동빔')


class MentorOwnedSlotTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.r=Rules(ROOT,ruleset='core')

    def fixture(self):
        case=QUOTA.MoveQuotaSafetyTests();case.r=self.r;case.setUp();return case

    def qualify(self,case,owner,features):
        owner.spec['skills']={'매력':3,'포켓몬학':6,'명령':4}
        owner.spec['feats']=['feat/멘토','feat/기술-가르침',*features]
        ITEMS.register_feats(case.e,owner)

    def trainer(self,case,name,features=()):
        owner=case.add(build_trainer(self.r,name,20,STATS,abilities=[]))
        self.qualify(case,owner,features);return owner

    def roster(self,case,owner,pokemon):
        return PARTY.configure(case.e,owner,mode='unlimited',reason='actual complete roster',roster=pokemon)

    def transfer(self,case,pokemon,old,new,request='slots/transfer'):
        return PARTY.transfer(case.e,old,target=pokemon,new_owner=new,
                              reason='actual Mentor ownership transfer',request_id=request)

    def assert_capacity(self,pokemon,feature):
        view=MOVES.describe(self.r,pokemon.spec)
        self.assertEqual(view['total' if MOVES.SLOT_POLICIES[feature]==MOVES.GUIDANCE else 'taught'],
                         7 if MOVES.SLOT_POLICIES[feature]==MOVES.GUIDANCE else 4)
        row=next(row for row in view['sources'] if row.get('rule_id')==feature)
        self.assertEqual(row['owner_id'],pokemon.spec['trainer_id'])

    def fill(self,case,pokemon,feature):
        if MOVES.SLOT_POLICIES[feature]==MOVES.GUIDANCE:
            for move in case.mids()[:7]:case.e.gm.set_move(pokemon,move,reason='actual known natural move')
            self.assertEqual(MOVES.describe(self.r,pokemon.spec)['slot_count'],7)
            return case.mids()[6]
        for move,method in zip(TAUGHT,('tm','tutor','feature','tutor')):
            case.observe(pokemon,move,method,1)
        self.assertEqual(MOVES.describe(self.r,pokemon.spec)['taught_count'],4)
        return self.r.move_id(TAUGHT[-1])

    def test_all_four_transfer_in_and_back_preserve_recipient_and_exact_owner_sources(self):
        for feature in FEATURES:
            with self.subTest(feature=feature):
                case=self.fixture();new=self.trainer(case,'recipient',[feature])
                pokemon=case.pokemon('이상해씨',50)
                resident=case.add(build_pokemon(self.r,'브케인',5,moves=[],abilities=[],extra={'trainer_id':new.entity_id}))
                self.roster(case,case.a,[pokemon]);self.roster(case,new,[resident])
                before=deepcopy(resident.spec);self.assert_capacity(resident,feature)
                self.transfer(case,pokemon,case.a,new);self.assert_capacity(pokemon,feature)
                self.assertEqual(resident.spec,before)
                self.transfer(case,pokemon,new,case.a,'slots/return')
                self.assertEqual((MOVES.describe(self.r,pokemon.spec)['total'],MOVES.describe(self.r,pokemon.spec)['taught']),(6,3))
                self.assertNotIn('feature:'+new.entity_id+':'+feature,pokemon.spec[GRANTS.KEY]['sources'])
                self.assertEqual(resident.spec,before)

    def test_same_feature_final_seven_or_four_survives_bidirectional_transfer_and_replay(self):
        for feature in (FEATURES[0],FEATURES[3]):
            with self.subTest(feature=feature):
                case=self.fixture();self.qualify(case,case.a,[feature]);new=self.trainer(case,'also qualified',[feature])
                pokemon=case.pokemon('이상해씨',50);self.roster(case,case.a,[pokemon]);self.roster(case,new,[])
                self.fill(case,pokemon,feature);history=deepcopy((pokemon.spec.get('move_learning'),pokemon.spec.get(MOVES.HISTORY),pokemon.spec.get('move_learning_log')))
                old_key='feature:'+case.a.entity_id+':'+feature;new_key='feature:'+new.entity_id+':'+feature
                receipt=self.transfer(case,pokemon,case.a,new);self.assert_capacity(pokemon,feature)
                self.assertIn(old_key,receipt['cleanup']['sources']);self.assertNotIn(new_key,receipt['cleanup']['sources'])
                self.assertNotIn(old_key,pokemon.spec[GRANTS.KEY]['sources']);self.assertIn(new_key,pokemon.spec[GRANTS.KEY]['sources'])
                before=CODEC.dump_engine(case.e);self.assertEqual(self.transfer(case,pokemon,case.a,new),receipt)
                self.assertEqual(CODEC.dump_engine(case.e),before)
                self.transfer(case,pokemon,new,case.a,'slots/back');self.assert_capacity(pokemon,feature)
                self.assertIn(old_key,pokemon.spec[GRANTS.KEY]['sources']);self.assertNotIn(new_key,pokemon.spec[GRANTS.KEY]['sources'])
                self.assertEqual((pokemon.spec.get('move_learning'),pokemon.spec.get(MOVES.HISTORY),pokemon.spec.get('move_learning_log')),history)

    def test_final_overcapacity_rolls_back_sources_refund_rosters_and_accepts_explicit_forget(self):
        for feature in (FEATURES[0],FEATURES[3]):
            with self.subTest(feature=feature):
                case=self.fixture();self.qualify(case,case.a,[feature]);new=self.trainer(case,'no slot feature')
                pokemon=case.pokemon('이상해씨',50);self.roster(case,case.a,[pokemon]);self.roster(case,new,[])
                last=self.fill(case,pokemon,feature)
                GRANTS.grant(pokemon,'capabilities','Jump=1','owner/refundable','feature',
                             owner_id=case.a.entity_id,lifetime='your_pokemon',rule_id='observed/owner-source',tutor_points=2)
                before=CODEC.dump_engine(case.e);points=pokemon.spec['tutor_points'];spec=pokemon.spec;registry=case.a.spec['pokemon_registry']
                with self.assertRaisesRegex(ValueError,'capacity'):self.transfer(case,pokemon,case.a,new)
                self.assertEqual(CODEC.dump_engine(case.e),before);self.assertIs(pokemon.spec,spec);self.assertIs(case.a.spec['pokemon_registry'],registry)
                case.e.gm.set_move(pokemon,last,add=False,reason='explicit forgotten move before ownership transfer')
                learning=deepcopy(pokemon.spec.get('move_learning'));receipt=self.transfer(case,pokemon,case.a,new)
                self.assertEqual(receipt['cleanup']['tutor_points_refunded'],2);self.assertEqual(pokemon.spec['tutor_points'],points+2)
                self.assertEqual(pokemon.spec.get('move_learning'),learning)
                self.assertNotIn('owner/refundable',pokemon.spec[GRANTS.KEY]['sources'])
                self.transfer(case,pokemon,case.a,new);self.assertEqual(pokemon.spec['tutor_points'],points+2)

    def test_later_gm_roster_projects_both_policies_idempotently_and_failure_is_atomic(self):
        for feature in (FEATURES[0],FEATURES[3]):
            with self.subTest(feature=feature):
                case=self.fixture();self.qualify(case,case.a,[feature]);pokemon=case.pokemon('이상해씨',50)
                self.assertEqual((MOVES.describe(self.r,pokemon.spec)['total'],MOVES.describe(self.r,pokemon.spec)['taught']),(6,3))
                self.roster(case,case.a,[pokemon]);self.assert_capacity(pokemon,feature)
                sources=deepcopy(pokemon.spec[GRANTS.KEY]['sources']);self.roster(case,case.a,[pokemon]);self.assertEqual(pokemon.spec[GRANTS.KEY]['sources'],sources)
                later=case.pokemon('브케인',5);before=CODEC.dump_engine(case.e)
                with patch.object(MOVES,'_require_slot_feature',side_effect=ValueError('selected slot source rejected')):
                    with self.assertRaisesRegex(ValueError,'selected slot'):self.roster(case,case.a,[pokemon,later])
                self.assertEqual(CODEC.dump_engine(case.e),before)

    def test_actual_throw_ball_projects_both_policies_and_keeps_capture_receipt_once(self):
        for feature in (FEATURES[0],FEATURES[3]):
            with self.subTest(feature=feature):
                case=FIRST.FirstOwnedSpeciesTests();case.r=self.r;case.setUp();self.qualify(case,case.a,[feature])
                self.roster(case,case.a,[]);pokemon=case.pokemon()
                self.assertTrue(case.catch(pokemon));self.assert_capacity(pokemon,feature)
                self.assertEqual(pokemon.spec['trainer_id'],case.a.entity_id)
                self.assertEqual(case.a.spec['exp_bank'],1);self.assertEqual(case.a.spec['items']['몬스터볼'],9)
                revision=case.a.spec['pokemon_registry_revision'];sources=deepcopy(pokemon.spec[GRANTS.KEY]['sources'])
                self.assertFalse(case.catch(pokemon));self.assertEqual(case.a.spec['exp_bank'],1)
                self.assertEqual(case.a.spec['items']['몬스터볼'],9);self.assertEqual(case.a.spec['pokemon_registry_revision'],revision)
                self.assertEqual(pokemon.spec[GRANTS.KEY]['sources'],sources)

    def test_actual_gift_and_hatch_projects_both_policies_without_changing_birth_history(self):
        for feature in (FEATURES[2],FEATURES[1]):
            with self.subTest(feature=feature):
                case=EGG.EggTests();case.r=self.r;case.setUp();egg=case.create()
                recipient=self.trainer(case,'gift recipient',[feature]);self.roster(case,recipient,[])
                case.e.gm.transfer_egg(case.a,recipient,egg['entity_id'],reason='actual egg gift',request_id='slots/egg-gift')
                result=case.e.hatch_declared_egg(recipient,egg['entity_id'],name='actual newborn',ready=True,
                                               reason='actual hatch observation',choices=case.choices())
                child=result['pokemon'];self.assert_capacity(child,feature)
                self.assertEqual(child.spec['move_learning']['move/뿌리박기']['teacher_id'],case.a.entity_id)
                self.assertEqual(child.spec['move_learning']['move/뿌리박기']['method'],'egg')
                self.assertEqual(child.spec['trainer_id'],recipient.entity_id)
                before=CODEC.dump_engine(case.e)
                with self.assertRaises(ValueError):case.e.hatch_declared_egg(recipient,egg['entity_id'],name='retry',ready=True,reason='retry',choices=case.choices())
                self.assertEqual(CODEC.dump_engine(case.e),before)

    def test_both_codecs_preserve_capacity_owner_source_and_transfer_replay(self):
        case=self.fixture();features=[MOVES.GUIDANCE,'C2CSV/input/db/feats.csv:R110:main']
        self.qualify(case,case.a,features);new=self.trainer(case,'combined recipient',features)
        pokemon=case.pokemon('이상해씨',50);self.roster(case,case.a,[pokemon]);self.roster(case,new,[])
        receipt=self.transfer(case,pokemon,case.a,new);expected=MOVES.describe(self.r,pokemon.spec)
        case.e.gm.snapshot('slots');self.transfer(case,pokemon,new,case.a,'slots/back');case.e.gm.restore('slots')
        actors=WORLD.actor_index(case.e);pokemon=actors[pokemon.entity_id]
        self.assertEqual(MOVES.describe(self.r,pokemon.spec),expected)
        fresh=Rules(ROOT,ruleset='core');loaded=CODEC.load_engine(fresh,json.loads(json.dumps(CODEC.dump_engine(case.e),ensure_ascii=False)))
        actors=WORLD.actor_index(loaded);restored=actors[pokemon.entity_id]
        self.assertEqual(MOVES.describe(fresh,restored.spec),expected);before=CODEC.dump_engine(loaded)
        self.assertEqual(PARTY.transfer(loaded,actors[case.a.entity_id],target=restored,new_owner=actors[new.entity_id],
                                      reason='actual Mentor ownership transfer',request_id='slots/transfer'),receipt)
        self.assertEqual(CODEC.dump_engine(loaded),before)

    def test_same_owner_rejection_and_selected_foiling_is_not_automatically_reissued(self):
        case=self.fixture();self.qualify(case,case.a,[MOVES.FOILING]);new=self.trainer(case,'new Guidance and unselected Foiling',[MOVES.GUIDANCE,MOVES.FOILING])
        pokemon=case.pokemon('이상해씨',50,case.mids()[:6]);self.roster(case,case.a,[pokemon]);self.roster(case,new,[])
        MOVES.select_foiling(case.e,case.a,pokemon,'씨뿌리기',reason='actual completed selection')
        case.e.gm.set_move(pokemon,'수면가루',reason='seventh known move under selected exemption')
        before=CODEC.dump_engine(case.e)
        with self.assertRaisesRegex(ValueError,'different trainer'):self.transfer(case,pokemon,case.a,case.a)
        self.assertEqual(CODEC.dump_engine(case.e),before)
        self.transfer(case,pokemon,case.a,new);view=MOVES.describe(self.r,pokemon.spec)
        self.assertEqual((view['total'],view['slot_count'],view['exempt']),(7,7,{}))
        self.assertEqual({row['rule_id'] for row in view['sources']},{MOVES.GUIDANCE})

    def test_new_guidance_still_rejects_actual_final_overflow_after_selected_exemption_loss(self):
        case=self.fixture();self.qualify(case,case.a,[MOVES.GUIDANCE,MOVES.FOILING])
        new=self.trainer(case,'receiving Guidance',[MOVES.GUIDANCE])
        pokemon=case.pokemon('이상해씨',50,case.mids()[:6]);self.roster(case,case.a,[pokemon]);self.roster(case,new,[])
        MOVES.select_foiling(case.e,case.a,pokemon,'씨뿌리기',reason='actual source-owned selected exemption')
        for move in case.mids()[6:]:case.e.gm.set_move(pokemon,move,reason='actual learned move under both old sources')
        self.assertEqual(len(MOVES.known(self.r,pokemon.spec)),8);before=CODEC.dump_engine(case.e)
        with self.assertRaisesRegex(ValueError,'capacity'):self.transfer(case,pokemon,case.a,new)
        self.assertEqual(CODEC.dump_engine(case.e),before)
        case.e.gm.set_move(pokemon,case.mids()[7],add=False,reason='explicit chosen eighth move forgotten')
        self.transfer(case,pokemon,case.a,new);view=MOVES.describe(self.r,pokemon.spec)
        self.assertEqual((view['total'],view['slot_count'],view['exempt']),(7,7,{}))

    def test_book_and_csv_rebind_their_distinct_selected_source_ids(self):
        for old_feature,new_feature in ((FEATURES[0],FEATURES[2]),(FEATURES[3],FEATURES[1])):
            with self.subTest(old=old_feature,new=new_feature):
                case=self.fixture();self.qualify(case,case.a,[old_feature]);new=self.trainer(case,'different selected source',[new_feature])
                pokemon=case.pokemon('이상해씨',50);self.roster(case,case.a,[pokemon]);self.roster(case,new,[])
                self.fill(case,pokemon,old_feature);self.transfer(case,pokemon,case.a,new)
                self.assert_capacity(pokemon,new_feature)
                self.assertEqual({row['rule_id'] for row in MOVES.describe(self.r,pokemon.spec)['sources']},{new_feature})

    def test_slot_source_failure_rolls_back_actual_capture_and_hatch_producers(self):
        for feature in (MOVES.GUIDANCE,):
            with self.subTest(feature=feature):
                case=FIRST.FirstOwnedSpeciesTests();case.r=self.r;case.setUp();self.qualify(case,case.a,[feature])
                self.roster(case,case.a,[]);pokemon=case.pokemon();before=CODEC.dump_engine(case.e)
                with patch.object(MOVES,'_require_slot_feature',side_effect=ValueError('slot source rejected')):
                    with self.assertRaisesRegex(ValueError,'slot source'):case.catch(pokemon)
                self.assertEqual(CODEC.dump_engine(case.e),before)
                case=EGG.EggTests();case.r=self.r;case.setUp();egg=case.create()
                recipient=self.trainer(case,'failure recipient',[feature]);self.roster(case,recipient,[])
                case.e.gm.transfer_egg(case.a,recipient,egg['entity_id'],reason='actual gift',request_id='slots/failure-egg')
                before=CODEC.dump_engine(case.e)
                with patch.object(MOVES,'_require_slot_feature',side_effect=ValueError('slot source rejected')):
                    with self.assertRaisesRegex(ValueError,'slot source'):
                        case.e.hatch_declared_egg(recipient,egg['entity_id'],name='child',ready=True,reason='actual hatch',choices=case.choices())
                self.assertEqual(CODEC.dump_engine(case.e),before)


if __name__=='__main__':unittest.main()
