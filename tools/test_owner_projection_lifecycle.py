"""Source-owned trainer projections at actual roster, capture and birth boundaries.

Declared sheets are the supported imported-acquisition route, not prerequisite
certification. Native Stat Ace, Species Savant and Type Ace receipts are tested
separately with the existing acquisition fixtures and their original XP banks.
"""
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import hashlib
import json
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'engine'), str(ROOT / 'tools')]
from builder import build_pokemon, build_trainer, species_lookup
from engine import Combatant, Engine, Rules
from ruleset import RuleFilter
import action_points as AP
import class_passive_combat as CLASS
import combat_precision_features as PRECISION
import items as ITEMS
import move_state as MOVES
import native_scenario_fixture as NATIVE
import pokemon_entities as ENTITIES
import pokemon_party as PARTY
import researcher_fields as RESEARCH
import state_codec as CODEC
import state_grants as GRANTS
import static_trainer_modifiers as STATIC
import trainer_feature_acquisition as ACQUIRE
import weapon_actions as WEAPONS
import world_entities as WORLD
import test_book_species_savant as SPECIES_FIX
import test_book_stat_ace_full as STAT_FIX
import test_book_type_ace_passives as TYPE_FIX
import test_book_researcher_fields_crafting as RESEARCH_FIX
import test_category2_static_trainer_modifiers as STATIC_FIX
import test_core_first_owned_species as CAPTURE_FIX
import test_foundation_egg_creation as EGG_FIX
import test_foundation_fossil_creation as FOSSIL_FIX

STATS = ('hp', 'atk', 'def', 'spa', 'spd', 'spe')
SHINE = 'feat/윤기나는-광택'
BOUNDARIES = ('late_join', 'capture', 'egg', 'fossil', 'artificial')
SLOTS = (MOVES.GUIDANCE, MOVES.LIFELONG,
         'C2CSV/input/db/feats.csv:R107:main', 'C2CSV/input/db/feats.csv:R110:main')


class OwnerProjectionLifecycleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rules = Rules(ROOT, ruleset='all')

    def add(self, e, spec, side='party'):
        actor = Combatant(e.r, spec)
        e.gm.add_combatant(actor, pos=(0, 0), side=side, reason='actual projection lifecycle participant')
        return actor

    def owner(self, e, sheet=None):
        extra = {'classes': [], 'feats': [], 'edges': [], 'items': {'몬스터볼': 10},
                 'type_link_skills': {'불꽃': '집중', '얼음': '생존'}}
        extra.update(deepcopy(sheet or {}))
        return self.add(e, build_trainer(e.r, 'actual projection owner', 30,
            dict.fromkeys(STATS, 12), abilities=[], moves=[],
            skills={'명령': 6, '집중': 4, '생존': 4, '매력': 3, '포켓몬학': 6}, extra=extra))

    def participant(self, e, owner=None, *, species='이상해씨', level=20, extra=None):
        fields = {} if owner is None else {'trainer_id': owner.entity_id}
        fields.update(extra or {})
        return self.add(e, build_pokemon(e.r, species, level, moves=[], abilities=[], extra=fields))

    def case(self, cls, *, rules=None):
        f = cls(); f.r = f.rules = rules or self.rules
        f.setUp(); self.addCleanup(f.doCleanups)
        return f

    def boundary(self, kind, sheet=None, *, placement='carried', species=None, owner_factory=None):
        """Prepare actual existing producers; return the still-unperformed join."""
        f = None
        if kind in ('late_join', 'capture'):
            f = self.case(CAPTURE_FIX.FirstOwnedSpeciesTests)
            e = f.e
            species = species or '잉어킹'
        elif kind == 'egg':
            f = self.case(EGG_FIX.EggTests); e = f.e
            if species is None:
                egg = f.create(); choices = f.choices(); species = '이상해씨'
            else:
                parents = [self.participant(e, f.a, species=species, level=5,
                    extra={'gender': gender}) for gender in ('female', 'male')]
                egg = e.create_declared_egg(f.a, parents, f.policy(), request_id='projection/ice-egg',
                    compatible=True, species=species, inheritance_moves=[], reason='actual selected parents')
                choices = dict(gender='male', nature='노력', abilities=[], moves=[],
                    special_appearance=False, inheritance_moves=[])
        elif kind == 'fossil':
            f = self.case(FOSSIL_FIX.FossilTests); e = f.e
            if species is not None:
                f.fossil = ENTITIES.prepare_fossil(e, f.a, 'projection-fossil',
                    {'species': species_lookup(e.r, species)['id'], 'status': 'fossil'})
                f.a.spec['fossils']['projection-fossil'] = f.fossil
            else:
                species = '암나이트'
            egg = f.default(gm_species_approved=True)['egg']
        elif kind == 'artificial':
            f = self.case(RESEARCH_FIX.ResearcherFieldsCraftingTests); e = f.e
            f.t.spec['items']['화학 세트'] = 1
            upgrades = [{'kind': 'shiny_contest', 'contest_stat': '근사함'},
                {'kind': 'inheritance_move', 'move': 'move/저주'},
                {'kind': 'base_stat', 'stat': 'spa'}, {'kind': 'base_stat', 'stat': 'spa'},
                {'kind': 'base_stat', 'stat': 'hp'}, {'kind': 'base_stat', 'stat': 'def'}]
            request = dict(species='코일', nature='겁쟁이', ability='옹골참', gender='무성',
                upgrades=upgrades, seconds=3600, reason='actual synthesis', request_id='projection/artificial')
            produced = RESEARCH.playing_god(e, f.t, **request)
            egg = ENTITIES.egg_index(e)[produced['egg_entity_id']][1]
            e.advance_time(86400, [f.t]); species = '코일'
        else:
            raise AssertionError(kind)
        owner = self.owner(e, sheet) if owner_factory is None else owner_factory(e, species)
        current = [p for p in WORLD.actors(e) if p.kind == 'pokemon' and p.spec.get('trainer_id') == owner.entity_id]
        if placement != 'pending':
            if placement == 'storage':
                PARTY.configure(e, owner, mode='custom', limit=0, roster=current,
                    storage={'kind': 'center', 'id': 'projection-center'}, reason='actual storage policy')
            else:
                PARTY.configure(e, owner, mode='unlimited', roster=current, reason='actual carrying policy')
        target = None
        if kind == 'late_join':
            target = Combatant(e.r, build_pokemon(e.r, species, 20, moves=[], abilities=[],
                extra={'trainer_id': owner.entity_id}))
            operation = lambda: e.gm.add_combatant(target, pos=(0, 0), side='party', reason='actual later owned join')
        elif kind == 'capture':
            target = f.pokemon(species)
            def operation():
                self.assertTrue(f.catch(target, trainer=owner))
                return target
        else:
            provider = f.t if kind == 'artificial' else f.a
            e.gm.transfer_egg(provider, owner, egg['entity_id'], reason='actual egg gift', request_id='projection/egg-gift')
            if kind == 'egg':
                operation = lambda: e.hatch_declared_egg(owner, egg['entity_id'], name='projection newborn',
                    ready=True, reason='actual hatch observation', choices=choices)['pokemon']
            elif kind == 'fossil':
                operation = lambda: e.hatch_restored_fossil(owner, egg['entity_id'], name='projection fossil newborn',
                    ready=True, reason='actual hatch observation', details=f.details())['pokemon']
            else:
                operation = lambda: RESEARCH.hatch_artificial(e, owner, egg['entity_id'],
                    name='projection artificial newborn', reason='actual hatch observation')['pokemon']
        return SimpleNamespace(e=e, owner=owner, run=operation, target=target, fixture=f,
            kind=kind, egg=egg if kind not in ('late_join', 'capture') else None)

    def shine(self, e, pokemon):
        return PRECISION.effect_natural(e, pokemon, e.r.move('move/아이언헤드'), 13)

    def assert_identity(self, b, p):
        self.assertIs(WORLD.actor_index(b.e)[p.entity_id], p)
        self.assertIs(next(q for q in b.e.everyone if q.entity_id == p.entity_id), p)
        self.assertIs(next(q for q in b.e.gm.everyone if q.entity_id == p.entity_id), p)
        self.assertEqual(p.spec['trainer_id'], b.owner.entity_id)
        if b.egg is not None:
            egg = ENTITIES.egg_index(b.e)[b.egg['entity_id']][1]
            self.assertTrue(egg['hatched']); self.assertEqual(egg['pokemon_id'], p.entity_id)
            self.assertEqual(p.spec['egg_entity_id'], egg['entity_id'])

    def test_all_six_csv_stat_formulas_reach_each_native_boundary_once(self):
        for field, (clause, source, branch) in STATIC_FIX.STAT_ROWS.items():
            for kind in BOUNDARIES:
                with self.subTest(field=field, boundary=kind):
                    sheet = {'classes': [source], 'feature_choices': {} if branch is None else {source: [branch]}}
                    b = self.boundary(kind, sheet); p = b.run(); self.assert_identity(b, p)
                    self.assertEqual(p.stats, {s: p.spec['stats'][s] + (1 + p.level // 10 if s == field else 0) for s in STATS})
                    rows = [r for r in GRANTS.state(p)['sources'].values() if r.get('clause_id') == clause]
                    self.assertEqual(len(rows), 1); self.assertEqual(rows[0]['owner_id'], b.owner.entity_id)
                    before = deepcopy((p.stats, p.modifiers, p.spec))
                    PARTY.project_current_owner(b.e, p); PARTY.project_current_owner(b.e, p)
                    self.assertEqual(before, (p.stats, p.modifiers, p.spec))

    def test_range_generic_shine_and_both_slot_source_identities_reach_every_boundary(self):
        for kind in BOUNDARIES:
            for slots in (SLOTS[:2], SLOTS[2:]):
                with self.subTest(boundary=kind, slots=slots):
                    sheet = {'classes': [STATIC.STAT_ACE],
                        'feats': [STATIC.STAT_MASTERY, SHINE, 'feat/멘토', 'feat/기술-가르침', *slots],
                        'feature_choices': {STATIC.STAT_ACE: ['spa'], STATIC.STAT_MASTERY: ['spa']}}
                    b = self.boundary(kind, sheet); p = b.run()
                    view = MOVES.describe(b.e.r, p.spec)
                    self.assertEqual((view['total'], view['taught']), (7, 4))
                    self.assertEqual({r['rule_id'] for r in view['sources']}, set(slots))
                    self.assertEqual(self.shine(b.e, p), 15)
                    self.assertEqual(PRECISION.effect_range_bonus(p, b.e.r.move('move/전기쇼크')), 0)
                    for name, origin, size in (('화염방사', 6, None), ('회오리', 8, 3), ('아이언헤드', 'melee', None)):
                        spec = WEAPONS.range_spec(b.e, b.e.r.move('move/' + name), p)
                        self.assertEqual(spec['origin'], origin)
                        if size is not None: self.assertEqual(spec['size'], size)
                    self.assert_identity(b, p)

    def test_class_fire_and_ice_declarations_preserve_live_type_and_target_conditions(self):
        for kind in BOUNDARIES:
            for ice in (False, True):
                if kind == 'artificial' and ice: continue  # No printed artificial-egg species has Ice type.
                with self.subTest(boundary=kind, ice=ice):
                    species = ('아마루스' if kind == 'fossil' else '바닐프티') if ice else None
                    b = self.boundary(kind, {'feats': [CLASS.SHINING_FLAME, CLASS.GLACIAL_ICE]}, species=species)
                    p = b.run(); enemy = self.participant(b.e, species='꼬부기')
                    fire = b.e.r.move('move/화염방사')
                    self.assertEqual(CLASS.damage_roll_modifier(b.e, p, enemy, fire, 1), 0)
                    b.e.apply_status(enemy, '화상', source='condition/화상', applied_by=b.owner)
                    self.assertEqual(CLASS.damage_roll_modifier(b.e, p, enemy, fire, 1), 4)
                    self.assertEqual(CLASS.damage_roll_modifier(b.e, p, enemy, dict(fire, type='물'), 1), 0)
                    self.assertEqual(CLASS.damage_reduction(b.e, enemy, p, fire, 2, False), 4 if ice else 0)
                    self.assertEqual(CLASS.damage_reduction(b.e, enemy, p, fire, 1, False), 0)
                    self.assertEqual(CLASS.damage_reduction(b.e, enemy, p, dict(fire, type='노말'), 2, False), 0)
                    for uid in (CLASS.SHINING_FLAME, CLASS.GLACIAL_ICE):
                        self.assertIn(CLASS._source_id(b.owner, p, uid), GRANTS.state(p)['sources'])

    def test_explicit_csv_class_passive_ids_keep_exact_acquisition_source(self):
        records = {CLASS.SPECIES_SAVANT: 7, CLASS.SHINING_FLAME: 253, CLASS.GLACIAL_ICE: 273}
        digest = hashlib.sha256((ROOT / 'input/db/feats.csv').read_bytes()).hexdigest()
        for uid, record in records.items():
            source = f'C2CSV/input/db/feats.csv:R{record}:main'
            self.assertEqual(self.rules._selected_rule(source), source)
            selected = self.rules.select_source_definition(source)
            self.assertEqual(selected['selected_id'], source)
            self.assertEqual(selected['source']['file'], 'db/feats.csv')
            self.assertEqual(selected['source']['record_span'], [record, record])
            self.assertEqual(selected['source']['sha256'], digest)
            for kind in BOUNDARIES:
                with self.subTest(source=source, boundary=kind):
                    ice = uid == CLASS.GLACIAL_ICE and kind != 'artificial'
                    species = ('아마루스' if kind == 'fossil' else '바닐프티') if ice else None
                    b = self.boundary(kind, {'feats': [source],
                        'class_passive_choices': {CLASS.SPECIES_SAVANT: {'evolution_group': 'accepted-family'}}},
                        species=species)
                    if uid == CLASS.SPECIES_SAVANT and b.target is not None:
                        b.target.spec['evolution_group'] = 'accepted-family'
                    p = b.run(); rows = GRANTS.state(p)['sources']
                    key = CLASS._source_id(b.owner, p, uid)
                    species_bonus = uid == CLASS.SPECIES_SAVANT and b.target is not None
                    if uid == CLASS.SPECIES_SAVANT and not species_bonus:
                        self.assertNotIn(key, rows)  # No authored CSV family label is invented at birth.
                    else:
                        self.assertEqual(rows[key]['acquisition_source'], source)
                        self.assertEqual(rows[key]['clause_id'], source)
                        self.assertNotIn('native_clause_id', rows[key])
                        self.assertNotIn('source_variant', rows[key])
                    self.assertEqual(p.stats, {stat: p.spec['stats'][stat] + int(species_bonus) for stat in STATS})
                    for other in records:
                        if other != uid:
                            self.assertNotIn(CLASS._source_id(b.owner, p, other), rows)
                    enemy = self.participant(b.e, species='꼬부기')
                    fire = b.e.r.move('move/화염방사')
                    b.e.apply_status(enemy, '화상', source='condition/화상', applied_by=b.owner)
                    self.assertEqual(CLASS.damage_roll_modifier(b.e, p, enemy, fire, 1),
                        4 if uid == CLASS.SHINING_FLAME else 0)
                    self.assertEqual(CLASS.damage_reduction(b.e, enemy, p, fire, 2, False), 4 if ice else 0)
                    before = deepcopy((p.spec[GRANTS.KEY], p.stats, p.modifiers))
                    PARTY.project_current_owner(b.e, p)
                    self.assertEqual((p.spec[GRANTS.KEY], p.stats, p.modifiers), before)

    def test_explicit_csv_passive_restore_preserves_source_and_exclusion_is_atomic(self):
        rules = Rules(ROOT, ruleset='all')
        fresh = Rules(ROOT, ruleset='all')
        with patch.object(self, 'rules', rules):
            for uid in (CLASS.SPECIES_SAVANT, CLASS.SHINING_FLAME, CLASS.GLACIAL_ICE):
                source = CLASS.CLAUSE_BY_RULE[uid]
                with self.subTest(source=source):
                    b = self.boundary('late_join', {'feats': [source],
                        'class_passive_choices': {CLASS.SPECIES_SAVANT: {'evolution_group': 'accepted-family'}}},
                        species='바닐프티' if uid == CLASS.GLACIAL_ICE else None)
                    b.target.spec['evolution_group'] = 'accepted-family'
                    p = b.run()
                    loaded = CODEC.load_engine(fresh, json.loads(json.dumps(CODEC.dump_engine(b.e), ensure_ascii=False)))
                    restored = WORLD.actor_index(loaded)[p.entity_id]
                    row = GRANTS.state(restored)['sources'][CLASS._source_id(b.owner, restored, uid)]
                    self.assertEqual(row['acquisition_source'], source)
                    self.assertEqual(loaded.r.select_source_definition(source)['source']['file'], 'db/feats.csv')
                    before = CODEC.dump_engine(loaded)
                    PARTY.project_current_owner(loaded, restored)
                    self.assertEqual(CODEC.dump_engine(loaded), before)
                    old = rules.ruleset
                    try:
                        profile = deepcopy(old.profile)
                        profile['exclude_units'] = [*profile.get('exclude_units', []), source]
                        rules.ruleset = RuleFilter(profile, name=old.name)
                        rules._apply_ruleset()
                        NATIVE.assert_rejected_unchanged(b.e, lambda: PARTY.project_current_owner(b.e, p),
                            reason_pattern='Excluded rule selection')
                    finally:
                        rules.ruleset = old
                        rules._apply_ruleset()

    def species_owner(self, e, species):
        f = SPECIES_FIX.BookSpeciesSavantTests(); f.rules = e.r; f.e = e
        owner = f.trainer('native family projection owner'); f.t = owner
        owner.spec.setdefault('items', {})['몬스터볼'] = 10
        trio = [f.pokemon(species) for _ in range(3)]
        f.acquire(trio, selected=species)
        return owner

    def test_native_species_receipt_projects_actual_family_on_all_birth_and_join_routes(self):
        for kind in BOUNDARIES:
            with self.subTest(boundary=kind):
                b = self.boundary(kind, owner_factory=self.species_owner); p = b.run()
                self.assertEqual(p.stats, {s: p.spec['stats'][s] + 1 for s in STATS})
                row = GRANTS.state(p)['sources'][CLASS._source_id(b.owner, p, CLASS.SPECIES_SAVANT)]
                self.assertEqual(row['source_variant'], 'C03-126')
                self.assertTrue(row['acquisition_receipt_id'])
                wrong = self.participant(b.e, b.owner, species='메타몽')
                self.assertEqual(wrong.stats, wrong.spec['stats'])
                self.assertNotIn(CLASS._source_id(b.owner, wrong, CLASS.SPECIES_SAVANT), GRANTS.state(wrong)['sources'])

    def test_csv_species_label_remains_distinct_and_wrong_or_absent_label_is_inert(self):
        for kind in ('late_join', 'capture'):
            for label, expected in (('fish-family', 1), ('other-family', 0), (None, 0)):
                with self.subTest(boundary=kind, label=label):
                    b = self.boundary(kind, {'feats': [CLASS.SPECIES_SAVANT],
                        'class_passive_choices': {CLASS.SPECIES_SAVANT: {'evolution_group': 'fish-family'}}})
                    if label is not None: b.target.spec['evolution_group'] = label
                    p = b.run()
                    self.assertEqual(p.stats, {s: p.spec['stats'][s] + expected for s in STATS})
                    self.assertFalse(ACQUIRE.receipts(b.owner))

    def type_owner(self, e, species):
        # Reuse the native fixture's exact initial sheet and XP budget, then its
        # public participant/acquisition helpers in this producer's actual world.
        template = self.case(TYPE_FIX.TypeAcePassiveTests, rules=e.r)
        template.e = e
        template.t = template.add('native Steel projection owner', 'trainer', (0, 0),
            classes=[], feats=[], exp_bank=100, items={'몬스터볼': 10}, type_link_skills={})
        template.p = template.add('Steel prerequisite one', 'pokemon', (0, 0), trainer_id=template.t.entity_id)
        template.q = template.add('Steel prerequisite two', 'pokemon', (0, 0), trainer_id=template.t.entity_id)
        template.family('강철', 'Polished Shine')
        return template.t

    def test_receipted_type_ace_shine_is_exactly_two_without_generic_double_projection(self):
        for kind in BOUNDARIES:
            with self.subTest(boundary=kind):
                b = self.boundary(kind, owner_factory=self.type_owner)
                receipts = deepcopy(ACQUIRE.receipts(b.owner)); p = b.run()
                self.assertEqual(self.shine(b.e, p), 15)
                self.assertEqual(PRECISION.effect_range_bonus(p, b.e.r.move('move/아이언헤드')), 0)
                self.assertNotIn('feature:' + b.owner.entity_id + ':' + SHINE, GRANTS.state(p)['sources'])
                PARTY.project_current_owner(b.e, p)
                self.assertEqual(self.shine(b.e, p), 15); self.assertEqual(ACQUIRE.receipts(b.owner), receipts)

    def test_native_stat_receipts_and_mastery_keep_the_book_source_at_late_join(self):
        for branch in ('atk', 'def', 'spa', 'spd', 'spe'):
            with self.subTest(branch=branch):
                f = self.case(STAT_FIX.StatAceTests)
                f.family(branch, mastery=branch == 'spa')
                p = self.participant(f.e, f.a)
                self.assertEqual(p.stats[branch], p.spec['stats'][branch] + 3)
                rows = GRANTS.state(p)['sources'].values()
                self.assertTrue(any(r.get('clause_id') == 'C04-047' for r in rows))
                self.assertFalse(any(r.get('clause_id') == STATIC_FIX.STAT_ROWS[branch][0] for r in rows))
                if branch == 'spa':
                    self.assertEqual(WEAPONS.range_spec(f.e, f.e.r.move('move/화염방사'), p)['origin'], 6)
                    self.assertTrue(any(r.get('clause_id') == 'input/ch04-trainer-classes.md:1131-1140' for r in rows))

    def stat_owner(self, e, species):
        template = self.case(STAT_FIX.StatAceTests, rules=e.r)
        sheets = [deepcopy(actor.spec) for actor in (template.a, template.p, template.q, template.r)]
        sheets[0]['items'] = {'몬스터볼': 10}
        template.e = e
        template.a, template.p, template.q, template.r = [self.add(e, sheet) for sheet in sheets]
        template.family('spa', mastery=True)
        return template.a

    def test_native_stat_mastery_receipts_survive_capture_and_all_birth_producers(self):
        for kind in BOUNDARIES[1:]:
            with self.subTest(boundary=kind):
                b = self.boundary(kind, owner_factory=self.stat_owner)
                receipts = deepcopy(ACQUIRE.receipts(b.owner)); p = b.run()
                self.assertEqual(p.stats['spa'], p.spec['stats']['spa'] + 1 + p.level // 10)
                self.assertEqual(WEAPONS.range_spec(b.e, b.e.r.move('move/화염방사'), p)['origin'], 6)
                clauses = {r.get('clause_id') for r in GRANTS.state(p)['sources'].values()}
                self.assertIn('C04-047', clauses)
                self.assertIn('input/ch04-trainer-classes.md:1131-1140', clauses)
                self.assertNotIn('C2CSV/input/db/feats.csv:R164:main', clauses)
                self.assertNotIn('C2CSV/input/db/feats.csv:R194:main', clauses)
                self.assertEqual(ACQUIRE.receipts(b.owner), receipts)

    def test_carried_storage_pending_all_acquire_effects_without_granting_combat_participation(self):
        for kind in BOUNDARIES[1:]:
            for location in ('carried', 'storage', 'pending'):
                with self.subTest(boundary=kind, location=location):
                    b = self.boundary(kind, {'classes': [STATIC.ENDURING], 'feats': [SHINE]}, placement=location)
                    p = b.run()
                    self.assertEqual(p.spec['party_location']['location'], location)
                    self.assertEqual(p.stats['hp'], p.spec['stats']['hp'] + 1 + p.level // 10)
                    self.assertEqual(self.shine(b.e, p), 15)
                    if location != 'carried':
                        self.assertFalse(p.on_field)
                        with self.assertRaisesRegex(ValueError, 'stored|unresolved'):
                            PARTY.require_participation(b.e, p)

    def test_same_side_foreign_owner_ownerless_and_unregistered_objects_do_not_borrow_sources(self):
        b = self.boundary('late_join', {'classes': [STATIC.ENDURING], 'feats': [SHINE]})
        other = self.owner(b.e)
        for owner in (None, other):
            p = self.participant(b.e, owner)
            self.assertEqual(p.stats, p.spec['stats']); self.assertEqual(self.shine(b.e, p), 13)
            self.assertFalse(any(r.get('owner_id') == b.owner.entity_id for r in GRANTS.state(p)['sources'].values()))
        before = CODEC.dump_engine(b.e); spec = deepcopy(b.target.spec)
        with self.assertRaisesRegex(ValueError, 'actual registered'):
            PARTY.project_current_owner(b.e, b.target)
        self.assertEqual(CODEC.dump_engine(b.e), before); self.assertEqual(b.target.spec, spec)
        p = b.run(); self.assertEqual(self.shine(b.e, p), 15)

    def test_failed_capture_and_invalid_thrower_never_install_owner_effects(self):
        for options in ({'fixed_accuracy': 1}, {'fixed_capture': 1}):
            with self.subTest(rolls=options):
                b = self.boundary('capture', {'classes': [STATIC.ENDURING], 'feats': [SHINE]})
                rolls = {'fixed_accuracy': 20, 'fixed_capture': 20, **options}
                self.assertFalse(b.e.throw_ball(b.owner, b.target, **rolls))
                attempts = b.owner.spec['capture_attempts']
                self.assertEqual(len(attempts), 1)
                self.assertEqual(next(iter(attempts.values()))['hit'], 'fixed_capture' in options)
                self.assertFalse(b.target.captured); self.assertNotIn('trainer_id', b.target.spec)
                self.assertEqual(b.target.stats, b.target.spec['stats']); self.assertEqual(self.shine(b.e, b.target), 13)
        b = self.boundary('capture', {'feats': [SHINE]})
        fake = Combatant(b.e.r, deepcopy(b.owner.spec))
        NATIVE.assert_rejected_unchanged(b.e, lambda: b.fixture.catch(b.target, trainer=fake), reason_pattern='actual registered')

    def test_birth_projections_preserve_inherited_moves_fossil_lineage_and_artificial_upgrades(self):
        for kind in ('egg', 'fossil', 'artificial'):
            with self.subTest(boundary=kind):
                b = self.boundary(kind, {'classes': [STATIC.ENDURING], 'feats': [SHINE]})
                b.e.everyone = list(b.e.gm.everyone)
                rosters = (b.e.everyone, b.e.gm.everyone)
                p = b.run(); self.assert_identity(b, p)
                self.assertIs(b.e.everyone, rosters[0]); self.assertIs(b.e.gm.everyone, rosters[1])
                if kind == 'egg':
                    self.assertEqual((p.level, p.spec['tutor_points']), (1, 1))
                    learned = p.spec['move_learning']['move/뿌리박기']
                    self.assertEqual((learned['method'], learned['teacher_id']), ('egg', b.fixture.a.entity_id))
                elif kind == 'fossil':
                    self.assertEqual(p.level, 10)
                    self.assertEqual(p.spec['fossil_entity_id'], b.fixture.fossil['entity_id'])
                    self.assertEqual(b.fixture.fossil['pokemon_id'], p.entity_id)
                else:
                    self.assertEqual((p.level, p.spec['nature'], p.abilities), (5, '겁쟁이', ['옹골참']))
                    self.assertEqual(p.spec['vitamin_bonus'], {'spa': 2, 'hp': 1, 'def': 1})
                    self.assertIn('move/저주', p.moves); self.assertEqual(b.fixture.t.spec['money'], 6500)
                NATIVE.assert_rejected_unchanged(b.e, b.run, reason_pattern='unhatched')

    def test_late_projection_failure_rolls_back_every_native_boundary_and_live_identity(self):
        for kind in BOUNDARIES:
            with self.subTest(boundary=kind):
                b = self.boundary(kind, {'classes': [STATIC.ENDURING], 'feats': [SHINE, MOVES.GUIDANCE]})
                before = CODEC.dump_engine(b.e); rulings = deepcopy(b.e.rulings.log)
                owner_spec = b.owner.spec; rosters = (b.e.everyone, b.e.gm.everyone)
                target_spec = None if b.target is None else b.target.spec
                original = ITEMS.project_owned_pokemon_features
                def fail(e, owner, targets):
                    result = original(e, owner, targets)
                    e.rng.random(); e.rulings.log.append({'test': 'discarded late projection ruling'})
                    raise ValueError('late owner projection failure')
                with patch.object(ITEMS, 'project_owned_pokemon_features', side_effect=fail):
                    with self.assertRaisesRegex(ValueError, 'late owner projection failure'): b.run()
                self.assertEqual(CODEC.dump_engine(b.e), before); self.assertEqual(b.e.rulings.log, rulings)
                self.assertIs(b.owner.spec, owner_spec)
                self.assertIs(b.e.everyone, rosters[0]); self.assertIs(b.e.gm.everyone, rosters[1])
                if b.target is not None: self.assertIs(b.target.spec, target_spec)
                p = b.run(); self.assert_identity(b, p); self.assertEqual(self.shine(b.e, p), 15)

    def test_capture_and_birth_do_not_replay_intrinsic_enter_or_trainer_registration(self):
        for kind in BOUNDARIES[1:]:
            with self.subTest(boundary=kind):
                b = self.boundary(kind, {'classes': [STATIC.ENDURING], 'feats': [SHINE, CLASS.RECKLESS]})
                payment = deepcopy((b.owner.spec.get('ap'), b.owner.spec.get('ap_bound'),
                    AP.available(b.owner), b.owner.spec.get('skills'), b.owner.spec.get('feats')))
                with (patch.object(Engine, 'register_abilities', side_effect=AssertionError('intrinsic re-entry')),
                      patch.object(ITEMS, 'register_feats', side_effect=AssertionError('trainer replay'))):
                    p = b.run()
                self.assertEqual(payment, (b.owner.spec.get('ap'), b.owner.spec.get('ap_bound'),
                    AP.available(b.owner), b.owner.spec.get('skills'), b.owner.spec.get('feats')))
                self.assertIsNone(CLASS._active(b.e, p, CLASS.RECKLESS))
                self.assertEqual(self.shine(b.e, p), 15)
                before = deepcopy((p.spec, p.stats, p.modifiers, p.moves, p.abilities))
                PARTY.project_current_owner(b.e, p)
                self.assertEqual(before, (p.spec, p.stats, p.modifiers, p.moves, p.abilities))

    def test_json_fresh_rules_and_gm_restore_preserve_each_boundary_without_double_grants(self):
        fresh = Rules(ROOT, ruleset='all')
        for kind in BOUNDARIES:
            with self.subTest(boundary=kind):
                b = self.boundary(kind, {'classes': [STATIC.ENDURING], 'feats': [SHINE, MOVES.GUIDANCE]})
                p = b.run(); expected = deepcopy((p.spec[GRANTS.KEY], p.stats, p.modifiers))
                snapshot = b.e.gm.snapshot()
                b.e.gm.set_level(p, p.level + 10, reason='actual temporary growth')
                b.e.gm.restore(snapshot)
                self.assertEqual((p.spec[GRANTS.KEY], p.stats, p.modifiers), expected)
                loaded = CODEC.load_engine(fresh, json.loads(json.dumps(CODEC.dump_engine(b.e), ensure_ascii=False)))
                restored = WORLD.actor_index(loaded)[p.entity_id]
                self.assertEqual((restored.spec[GRANTS.KEY], restored.stats, restored.modifiers), expected)
                PARTY.project_current_owner(loaded, restored)
                self.assertEqual((restored.spec[GRANTS.KEY], restored.stats, restored.modifiers), expected)
                self.assertEqual(self.shine(loaded, restored), 15)
                if kind == 'capture':
                    expected = CODEC.dump_engine(b.e)
                    engine_node = expected['nodes'][expected['root']['$ref']]
                    fields = dict(expected['nodes'][engine_node['attrs']['$ref']]['items'])
                    # A refused recapture emits one diagnostic; every other saved field stays unchanged.
                    expected['nodes'][fields['log_lines']['$ref']]['items'].append(
                        f'    {p.name}: 기절했거나 이미 주인이 있어 포획 불가  => [pokemon/capture-rate]')
                    self.assertFalse(b.fixture.catch(p, trainer=b.owner))
                    self.assertEqual(CODEC.dump_engine(b.e), expected)

    def test_newly_projected_book_species_retraining_and_transfer_remove_only_old_owner(self):
        for kind in ('capture', 'egg'):
            with self.subTest(boundary=kind):
                b = self.boundary(kind, owner_factory=self.species_owner); p = b.run()
                b.e.retrain_trainer_source(b.owner, CLASS.SPECIES_SAVANT, request_id='projection/withdraw',
                    reason='actual retraining', gm_decision={'allowed': True, 'reason': 'GM reviewed removal'}, retained_dependencies={})
                self.assertEqual(p.stats, p.spec['stats'])
                PARTY.project_current_owner(b.e, p); self.assertEqual(p.stats, p.spec['stats'])
        b = self.boundary('capture', {'classes': [STATIC.ENDURING], 'feats': [SHINE, MOVES.GUIDANCE]})
        p = b.run(); new = self.owner(b.e)
        PARTY.configure(b.e, new, mode='unlimited', roster=[], reason='actual recipient roster')
        receipt = PARTY.transfer(b.e, b.owner, target=p, new_owner=new, reason='actual later transfer', request_id='projection/transfer')
        self.assertEqual(p.stats, p.spec['stats']); self.assertEqual(self.shine(b.e, p), 13)
        self.assertEqual(MOVES.describe(b.e.r, p.spec)['total'], 6)
        before = CODEC.dump_engine(b.e)
        self.assertEqual(PARTY.transfer(b.e, b.owner, target=p, new_owner=new,
            reason='actual later transfer', request_id='projection/transfer'), receipt)
        self.assertEqual(CODEC.dump_engine(b.e), before)


if __name__ == '__main__':
    unittest.main()
