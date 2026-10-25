"""
PTK 콘테스트 엔진 (A층 #2). 전투 엔진과 같은 원칙: 수치·표·효과는 data/contest-rules.json 에서 읽고, 로그마다 근거 id.

  python -X utf8 -I engine/contest.py <experiment_root> [seed]
"""
import argparse
from copy import copy, deepcopy
import json
import os
import random
import sys
import uuid

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import arithmetic_policy as M
from ruleset import RuleFilter, RuleSelection, source_unit, UnresolvedRuleSelection, ExcludedRuleSelection
from resolution_transaction import resolve_transaction
from common_checks import dice
import contest_features as CONTEST_FEATURES
import action_points as AP
import roll_pools as POOLS
import turn as TURN
import contest_rotation as ROTATION
import contest_festival as FESTIVAL
import cosmetic_specimen as COSMETIC
import contest_halls as HALLS


class ContestRules:
    def __init__(self, root, ruleset=None):
        self.root = root
        self.ruleset = ruleset if isinstance(ruleset, RuleFilter) else RuleFilter.load(root, ruleset)
        with open(os.path.join(root, "data/contest-rules.json"), encoding="utf-8") as handle:
            units = json.load(handle)["units"]
        with open(os.path.join(root, "output/entities/moves.json"), encoding="utf-8") as handle:
            moves = json.load(handle)
        self._units = self._index(units)
        self._moves = self._index(moves)
        # The catalog validates profile references outside this reader's domain.
        # Runtime records replace provenance only for their exact identity; there
        # is deliberately no inferred db/core source for an unlabelled record.
        catalog = {}
        catalog_path = os.path.join(root, "output/ruleunits.jsonl")
        if os.path.exists(catalog_path):
            with open(catalog_path, encoding="utf-8") as handle:
                catalog = self._index([json.loads(line) for line in handle if line.strip()])
        catalog.update(self._units)
        catalog.update(self._moves)
        self.selection = RuleSelection(self.ruleset, [source_unit(u) for u in catalog.values()])
        self.selection.validate_choices()

    def _selected_rule(self, uid, supports_versions=False):
        self.selection.require_current_filter(self.ruleset)
        return self.selection.require_supported_version(uid, supports_versions)

    @staticmethod
    def _index(records):
        result = {}
        for record in records:
            uid = record.get("id")
            if not isinstance(uid, str) or not uid or uid in result:
                raise ValueError("Missing or duplicate contest reader identity: " + str(uid))
            result[uid] = deepcopy(record)
        return result

    @property
    def units(self):
        """Detached selected view. Mutating it cannot alter the reader's source data."""
        result = {}
        for uid in self._units:
            try:
                selected = self.selection.resolve(uid)
                record = deepcopy(self._units[selected])
                record["mech"]["data"] = self.mech(uid)
                result[uid] = record
            except (ExcludedRuleSelection, UnresolvedRuleSelection):
                continue
        return result

    @property
    def moves(self):
        """Legacy name lookup view; unresolved/excluded names are not executable."""
        result = {}
        for name in {m["name"] for m in self._moves.values()}:
            try:
                result[name] = self.move(name)
            except (ExcludedRuleSelection, UnresolvedRuleSelection):
                continue
        return result

    def mech(self, uid):
        self.selection.require_current_filter(self.ruleset)
        selected = self.selection.resolve(uid)
        if selected not in self._units:
            raise UnresolvedRuleSelection(selected, ["contest_mechanics_not_loaded"])
        return deepcopy(self.ruleset.mech_version(selected, self._units[selected]["mech"]["data"]))

    def move(self, identity_or_name):
        import coordinator as COORD
        row=COORD.innovation_instance(self,identity_or_name)
        if row is not None:return COORD.definition(self,identity_or_name,row)
        row=COORD.adaptable_instance(self,identity_or_name)
        if row is not None:return COORD.adaptable_definition(self,identity_or_name,row)
        self.selection.require_current_filter(self.ruleset)
        if identity_or_name in self.selection.units or identity_or_name.startswith("move/"):
            selected = self.selection.resolve(identity_or_name)
        else:
            selected = self.selection.resolve_name(identity_or_name, ("move/",))
        self.selection.require_supported_version(selected)
        if selected not in self._moves:
            raise UnresolvedRuleSelection(selected, ["contest_move_record_not_loaded"])
        return deepcopy(self._moves[selected])

    def move_contest(self, identity_or_name):
        """Selected (contest stat, effect); accepts saved exact IDs and unique names."""
        c = self.move(identity_or_name).get("contest")
        if not isinstance(c, str) or " - " not in c:
            raise UnresolvedRuleSelection(identity_or_name, ["missing_contest_metadata"])
        stat, _, eff = c.partition(" - ")
        return stat.strip(), eff.strip().rstrip("!")

    def performance_rules(self):
        M.validate_source(self)
        # Selection/version errors must precede even last_move, logs or RNG writes.
        return {name: self.mech("contest/" + name) for name in (
            "performance-stage", "effects", "excitement", "type-match", "stat-dice", "appeal-scoring")}


class Contestant:
    @property
    def entity_id(self):
        """Stable participant identity; the bound native actor has its own ID."""
        return self._contestant_id

    @property
    def excitement(self):
        return self._paired_state['excitement'] if hasattr(self,'_paired_state') else self._excitement

    @excitement.setter
    def excitement(self,value):
        if hasattr(self,'_paired_state'):self._paired_state['excitement']=value
        else:self._excitement=value

    @property
    def double_next(self):
        return self._paired_state['double_next'] if hasattr(self,'_paired_state') else self._double_next

    @double_next.setter
    def double_next(self,value):
        if hasattr(self,'_paired_state'):self._paired_state['double_next']=value
        else:self._double_next=value

    @property
    def immune_fumble(self):
        return self._paired_state['immune_fumble'] if hasattr(self,'_paired_state') else self._immune_fumble

    @immune_fumble.setter
    def immune_fumble(self,value):
        if hasattr(self,'_paired_state'):self._paired_state['immune_fumble']=value
        else:self._immune_fumble=value

    def __init__(self, name, stat_dice, moves, intro_skill, intro_rank_dice, intro_stat, *,
                 intro_sources=(), intro_bonuses=(), trainer_edges=()):
        self._contestant_id = "contestant/" + str(uuid.uuid4())
        self.name = name
        self.stat_dice = dict(stat_dice)      # 남은 콘테스트 스탯 주사위 {"귀여움": 4, ...}
        self.moves = list(moves)  # Freeze the declared learned set against native list mutation.
        self.intro_skill, self.intro_rank_dice, self.intro_stat = intro_skill, intro_rank_dice, intro_stat
        self.intro_completed = False
        self.intro_sources = set(intro_sources)
        self.intro_bonuses = deepcopy(list(intro_bonuses))
        self.trainer_edges = set(trainer_edges)
        self.appeal = 0
        self.fumble = 0
        self.excitement = 0
        self.letter = None
        self.last_move = None
        self.been_center = False
        self.double_next = False
        self.immune_fumble = False

    def __repr__(self):
        return f"{self.name}[어필 {self.appeal} 펌블 {self.fumble} 흥분도 {self.excitement} 스탯주사위 {self.stat_dice}]"


class ContestEngine:
    def __init__(self, rules, seed=1, apply_intro_bonus=True):
        self.r = rules
        self.rng = random.Random(seed)
        self.log_lines = []
        self.apply_intro_bonus = apply_intro_bonus
        self._native_intro_bindings = {}
        self._trainer_partners = {}
        self._flourish_used = set()
        self._performance_observations = {}
        self._coordinator_used = set()  # Native (engine, trainer ID), once in this contest.
        self._adaptable_uses = {}
        self._fashion_used = set()      # (Pokemon, physical item, rule), once in this contest.
        self._paired_run = None
        self._paired_busy = False
        self._standard_run = None
        self._standard_busy = False
        self._festival_run = None
        self._festival_busy = False
        self._trainer_interactions = None
        self._snapshots = {}

    def log(self, msg, rule=None):
        self.log_lines.append(msg + (f"  => [{rule}]" if rule else ""))

    def d6(self, n):
        return POOLS.pool(self.rng, n)['faces']

    def clamp_ex(self, c, delta):
        ex = self.r.mech("contest/excitement")
        before = c.excitement
        c.excitement = max(ex["min"], min(ex["max"], c.excitement + delta))
        if c.excitement != before:
            self.log(f"    {c.name} 흥분도 {before} → {c.excitement}", "contest/excitement")
        return before - c.excitement if delta < 0 else c.excitement - before

    def stat_pool_from_combatant(self, pokemon, *, smart_stat_policy=None, trainer=None, engine=None):
        """Unstaged combat stats plus recorded consumed Poffins, for a new contest.

        PTK ch08:26 prints Defense for Smart; PTU 1.05 p262 prints Special
        Defense. Neither correction nor a campaign choice is inferred here.
        pokemon.spec['poffins'] is the ordered list of already consumed Poffins;
        Grace availability uses the current owner while keeping the consumed history.
        """
        M.validate_source(self.r)
        rule = self.r.mech("contest/stat-dice")
        if pokemon.kind != "pokemon":
            raise ValueError("Pokemon contest stats require a Pokemon")
        if smart_stat_policy not in ("ptk-literal-defense", "ptu-original-special-defense"):
            raise UnresolvedRuleSelection("contest/stat-dice", ["smart_stat_translation_choice_required"])
        mapping = dict(rule["stat_map"])
        mapping["슬기로움"] = "def" if smart_stat_policy == "ptk-literal-defense" else "spd"
        result = {}
        for stat, combat in mapping.items():
            value = pokemon.stats.get(combat)
            if type(value) is not int or value < 0:
                raise ValueError("Unstaged combat stat must be a non-negative integer")
            result[stat] = min(rule["max_from_combat_stat"], M.ratio(value,rule["per_combat_stat_points"]))
        if type(pokemon.level) is not int or not 1 <= pokemon.level <= 100:
            raise ValueError("Pokemon level must be an integer from 1 to 100")
        import poffin_state as POFFINS
        for stat in POFFINS.available(pokemon,trainer,engine=engine):
            result[stat] += rule["poffin_die"]
        actual_trainer=POFFINS.current_owner(engine,pokemon,trainer)
        if actual_trainer is not None:
            import contest_features as CF
            if CF.owned(actual_trainer,CF.STYLE):
                if engine is None:raise ValueError("Style Expert contest dice require the native world and current owner")
                for stat,dice in CF.style_stat_dice(engine,actual_trainer,pokemon).items():
                    result[stat]+=dice
        return result

    def contestant_from_combatants(self, engine, pokemon, trainer, intro_skill,
                                   stat_dice=None, *, intro_stat=None, bonus_stats=None,
                                   smart_stat_policy=None):
        """Bind introduction to native equipped items, skill rank and dated grooming.

        The contest pool is explicit until DOMAIN-037's translated stat conflict
        is resolved. Source availability is rechecked immediately before rolling.
        """
        native_pool = stat_dice is None
        if native_pool:
            stat_dice = self.stat_pool_from_combatant(pokemon, smart_stat_policy=smart_stat_policy, trainer=trainer, engine=engine)
        binding = (engine, pokemon, trainer, intro_skill, dict(bonus_stats or {}))
        rank, edges, sources, bonuses = self._native_intro_state(binding)
        rule = self.r.mech("contest/intro-stage")
        c = Contestant(pokemon.name, stat_dice, [mid for mid in pokemon.moves if mid!="struggle"], intro_skill, rank,
                       intro_stat or rule["skill_to_stat"][intro_skill],
                       trainer_edges=edges, intro_sources=sources, intro_bonuses=bonuses)
        self._native_intro_bindings[c] = binding
        if native_pool:
            bonuses=CONTEST_FEATURES.style_stat_dice(engine,trainer,pokemon)
            c._native_style_dice={stat:{"base":value-bonuses.get(stat,0),"visible":value,"bonus":bonuses.get(stat,0)}
                                  for stat,value in stat_dice.items()}
        return c

    def _refresh_native_style_dice(self, contestant):
        primary=contestant if contestant in self._native_intro_bindings else next(
            (c for c,partner in self._trainer_partners.items() if partner is contestant),None)
        if primary is None:return
        engine,pokemon,trainer,_,_=self._native_intro_bindings[primary]
        CONTEST_FEATURES.owner(trainer,pokemon)
        rows=getattr(primary,"_native_style_dice",None)
        if rows is None:return  # An explicitly supplied pool has its own authority.
        if not isinstance(rows,dict) or set(rows)!=set(primary.stat_dice):
            raise ValueError("native Style Expert dice contribution state is malformed")
        bonuses=CONTEST_FEATURES.style_stat_dice(engine,trainer,pokemon)
        planned={}
        for stat,row in rows.items():
            if not isinstance(row,dict) or set(row)!={"base","visible","bonus"} or any(type(value)is not int for value in row.values()):
                raise ValueError("native Style Expert dice contribution record is malformed")
            if row["bonus"] not in (0,2) or row["visible"]!=max(0,row["base"]+row["bonus"]):
                raise ValueError("native Style Expert dice contribution authority disagrees")
            current=primary.stat_dice[stat]
            if type(current)is not int or current<0:raise ValueError("remaining contest dice must be nonnegative integers")
            # Ordinary spending and introduction gains change the independent
            # balance. Keeping a negative hidden balance prevents remove/re-add
            # of a depleted source from refreshing dice already spent.
            base=row["base"]+current-row["visible"];bonus=bonuses.get(stat,0)
            planned[stat]={"base":base,"bonus":bonus,"visible":max(0,base+bonus)}
        for stat,row in planned.items():
            rows[stat]=row;primary.stat_dice[stat]=row["visible"]

    def _native_intro_state(self, binding):
        from skill_modifiers import rank
        engine, pokemon, trainer, skill, choices = binding
        if pokemon.kind != "pokemon" or trainer.kind != "trainer":
            raise ValueError("Introduction needs an actual Pokemon and Trainer")
        owner = trainer.spec.get("id")
        if not owner or pokemon.spec.get("trainer_id") != owner:
            raise ValueError("Contest Pokemon ownership must be established")
        skill = __import__('hobbyist').direct_skill(trainer,'edge/우아함',skill)
        n = rank(engine.r, trainer, skill)[2]
        edges = set()
        import poffin_state as POFFINS
        if POFFINS.grace(pokemon,trainer,engine=engine):
            edges.add("edge/우아함")
        sources, bonuses = set(), []
        for actor, source in ((pokemon, "item/콘테스트-장신구"), (trainer, "item/멋진-옷")):
            if any(x.get("item_id") == source for x in getattr(actor, "_item_reg", {}).values()):
                engine.r._selected_rule(source)
                if source not in choices:
                    raise ValueError("Equipped introduction bonus needs a chosen contest stat")
                sources.add(source)
                bonuses.append({"source_id": source, "stat": choices[source]})
        grooming = pokemon.spec.get("grooming", {})
        day = pokemon.spec.get("frequency_state", {}).get("day", 0)
        if grooming.get("source") == "edge/미용사" and grooming.get("day") == day:
            if grooming.get("trainer_id") != owner or grooming.get("intro_dice") != 1:
                raise ValueError("Grooming grant has unresolved ownership or dice")
            engine.r._selected_rule("edge/미용사")
            source = "edge/미용사"
            if source not in choices:
                raise ValueError("Active grooming bonus needs a chosen contest stat")
            sources.add(source)
            bonuses.append({"source_id": source, "stat": choices[source]})
        for source in CONTEST_FEATURES.INTRODUCTION_SKILL_BONUSES:
            if source in choices:
                count = CONTEST_FEATURES.introduction_bonus_dice(engine, trainer, pokemon, source)
                sources.add(source)
                bonuses.append({'source_id': source, 'stat': choices[source], 'dice': count})
        import researcher_fields as RESEARCH
        if RESEARCH.PLAYING_GOD in choices:
            count = RESEARCH.introduction_bonus_dice(engine, pokemon, choices[RESEARCH.PLAYING_GOD])
            sources.add(RESEARCH.PLAYING_GOD)
            bonuses.append({'source_id': RESEARCH.PLAYING_GOD, 'stat': choices[RESEARCH.PLAYING_GOD], 'dice': count})
        if COSMETIC.SOURCE in choices:
            count = COSMETIC.introduction_dice(engine, pokemon)
            sources.add(COSMETIC.SOURCE)
            bonuses.append({'source_id': COSMETIC.SOURCE, 'stat': choices[COSMETIC.SOURCE], 'dice': count})
        if set(choices) != sources:
            raise ValueError("Introduction choice has no currently active source")
        return n, edges, sources, bonuses

    # ---------- 소개 단계 ----------
    def intro_stage(self, contestants, contest_type):
        """Roll introduction rank dice and granted, source-labelled bonus dice.

        intro_sources names equipped items / an active grooming grant; admission
        and expiry of those grants belong to their originating item/training rule.
        No ordinary skill flat modifier is added to these individual d6 results.
        """
        rule = self.r.mech("contest/intro-stage")
        stats = self.r.mech("contest/type-match")["ring"]
        if contest_type not in stats and contest_type is not None:
            raise ValueError("Unknown contest type")
        if not 1 <= len(contestants) <= 5 or len({id(c) for c in contestants}) != len(contestants):
            raise ValueError("Introduction requires distinct contestants")
        native_pokemon = [self._native_intro_bindings[c][1] for c in contestants if c in self._native_intro_bindings]
        if len({id(c) for c in native_pokemon}) != len(native_pokemon):
            raise ValueError("The same native Pokemon cannot occupy two contest slots")
        plans = []
        for c in contestants:
            if c.intro_completed:
                raise ValueError("Introduction was already completed for this contestant")
            binding = self._native_intro_bindings.get(c)
            if binding is not None:
                current = self._native_intro_state(binding)
                if set(c.moves) != {mid for mid in binding[1].moves if mid != "struggle"}:
                    raise ValueError("Pokemon learned Moves changed; rebuild the declaration")
                if current != (c.intro_rank_dice, c.trainer_edges, c.intro_sources, c.intro_bonuses):
                    raise ValueError("Native introduction state changed; rebuild the declaration")
            if c.intro_skill not in rule["skill_to_stat"]:
                raise ValueError("Introduction requires one of the five contest skills")
            if type(c.intro_rank_dice) is not int or c.intro_rank_dice < 1:
                raise ValueError("Introduction requires an explicitly declared positive skill rank")
            if c.intro_rank_dice > 6 and c not in self._native_intro_bindings:
                raise ValueError("Seven-plus introduction rank needs its actual declared native skill source")
            stat = c.intro_stat or rule["skill_to_stat"][c.intro_skill]
            if stat not in stats:
                raise ValueError("Unknown introduction stat")
            if stat != rule["skill_to_stat"][c.intro_skill]:
                if "edge/우아함" not in c.trainer_edges or c.intro_rank_dice < 3:
                    raise ValueError("Introduction skill/stat substitution requires eligible Grace")
                self.r.selection.require_supported_version("edge/우아함")
            bonuses, seen = [], set()
            for bonus in c.intro_bonuses:
                source = bonus.get("source_id")
                if source not in c.intro_sources or source in seen:
                    raise ValueError("Introduction bonus needs a distinct active source")
                count = {"item/콘테스트-장신구": 2, "item/멋진-옷": 2, "edge/미용사": 1}.get(source)
                if source in CONTEST_FEATURES.INTRODUCTION_SKILL_BONUSES:
                    if binding is None:
                        raise ValueError('Acquired introduction feature needs its actual trainer and Pokemon')
                    engine, pokemon, trainer, _, _ = binding
                    count = CONTEST_FEATURES.introduction_bonus_dice(engine, trainer, pokemon, source)
                if source == COSMETIC.SOURCE:
                    if binding is None:
                        raise ValueError('Shiny introduction needs its actual native specimen')
                    engine, pokemon, trainer, _, _ = binding
                    count = COSMETIC.introduction_dice(engine, pokemon)
                if count is None:
                    raise UnresolvedRuleSelection(source, ["unsupported_introduction_bonus"])
                self.r.selection.require_supported_version(source)
                target = bonus.get("stat")
                if target not in stats:
                    raise ValueError("A bonus roll must choose its contest stat")
                if "dice" in bonus and (type(bonus["dice"]) is not int or bonus["dice"] != count):
                    raise ValueError("Introduction bonus dice disagree with their source")
                bonuses.append((source, target, count))
                seen.add(source)
            plans.append((stat, bonuses))

        def resolve(actors, rng):
            staged = copy(self)
            staged.rng, staged.log_lines = rng, []
            counts = []
            for c, (stat, bonuses) in zip(actors, plans):
                rolls = staged.d6(c.intro_rank_dice)
                n = sum(x >= 3 for x in rolls)
                c.stat_dice[stat] = c.stat_dice.get(stat, 0) + n
                total = n
                appeal = 0
                if rule["skill_to_stat"][c.intro_skill] == contest_type and self.apply_intro_bonus:
                    appeal = rule["matching_skill_bonus_appeal"]
                    c.appeal += appeal
                staged.log(f"  {c.name} 소개: {c.intro_skill} {c.intro_rank_dice}d6 {rolls} → {stat} 주사위 +{n}" + (f", 시작 어필 +{appeal}" if appeal else ""), "contest/intro-stage")
                for source, target, count in bonuses:
                    rolls = staged.d6(count)
                    gained = sum(x >= 3 for x in rolls)
                    c.stat_dice[target] = c.stat_dice.get(target, 0) + gained
                    total += gained
                    staged.log(f"    소개 보너스 {count}d6 {rolls} → {target} 주사위 +{gained}", source)
                counts.append((total + appeal, c))
            counts.sort(key=lambda t: -t[0])
            # Coin flips only resolve introduction ties, never final standings.
            for i in range(1, len(counts)):
                j = i
                while j and counts[j][0] == counts[j - 1][0]:
                    coin = staged.d6(1)[0]
                    staged.log(f"  소개 동률 동전: {'앞면' if coin <= 3 else '뒷면'}", "contest/intro-stage")
                    if coin <= 3:
                        break
                    counts[j - 1], counts[j] = counts[j], counts[j - 1]
                    j -= 1
            for i, (_, c) in enumerate(counts):
                c.letter = "ABCDE"[i]
                c.intro_completed = True
            staged.log("  문자 배정: " + ", ".join(f"{c.name}={c.letter}" for _, c in counts), "contest/intro-stage")
            return staged.log_lines

        self.log_lines.extend(resolve_transaction(contestants, self.rng, resolve))

    # ---------- 공연 ----------
    def type_mod(self, move_stat, contest_type):
        tm = self.r.mech("contest/type-match")
        ring = tm["ring"]
        if move_stat not in ring or contest_type not in ring:
            raise ValueError("Unknown contest move/type stat")
        if move_stat == contest_type:
            return tm["match_dice"], "일치"
        d = abs(ring.index(move_stat) - ring.index(contest_type)) if move_stat in ring else 0
        d = min(d, len(ring) - d)
        if d == 2:
            return tm["opposing_dice"], "대항"
        return 0, "연합"

    @staticmethod
    def validate_d6(rolls, expected_count=None):
        if not isinstance(rolls, (list, tuple)):
            raise ValueError("Contest rolls must be a list or tuple of d6 results")
        dice(rolls, expected_count)

    def score(self, rolls, center, override=None, mode="normal"):
        self.validate_d6(rolls)
        table = self.r.mech("contest/appeal-scoring")["center" if center else "normal"]
        import roll_pools as POOLS
        scored=POOLS.score_faces(rolls,table,dimensions=('appeal','fumble'),override=override)
        return scored['totals']['appeal'],scored['totals']['fumble']

    def _feature_binding(self, contestant, feature_sponsor=None):
        binding = self._native_intro_bindings.get(contestant)
        if binding is None:
            primary = next((c for c, partner in self._trainer_partners.items()
                            if partner is contestant), None)
            binding = self._native_intro_bindings.get(primary)
        if binding is None:
            raise ValueError("Contest feature requires a native trainer binding")
        engine, pokemon, trainer, skill, choices = binding
        CONTEST_FEATURES.owner(trainer, pokemon)
        if contestant in self._trainer_partners or contestant in self._trainer_partners.values():
            self._validate_pair_binding(binding)
        if feature_sponsor is not None:
            # ch08:269 changes the beneficiary, never the acquired source's
            # ownership or prerequisites. Select another actual team binding.
            state = self._standard_run
            if (state is None or "rotation" not in state or
                    state["phase"] != "perform" or not self._standard_busy):
                raise ValueError("feature sponsorship requires the current rotation performance")
            rotation = state["rotation"]
            team = next((team for team in rotation["teams"] if contestant in team), ())
            if feature_sponsor not in team or contestant not in rotation["current"].values():
                raise ValueError("feature sponsor must belong to the performer's actual rotation team")
            source = self._native_intro_bindings.get(feature_sponsor)
            if source is None or source[0] is not engine:
                raise ValueError("feature sponsor requires the same actual native contest")
            for rules in (self.r, engine.r):
                rules.selection.require_supported_version("ch08-contests/비전통적인-콘테스트-형식/로테이션-콘테스트")
            self._validate_native_binding(binding)
            self._validate_native_binding(source)
            binding = source
        return binding

    def _coordinator_owner(self, contestant, feature_sponsor=None):
        """Validate a currently acquired native Coordinator and its prerequisites."""
        self.r.selection.require_supported_version("class/코디네이터")
        self.r.selection.require_supported_version("edge/우아함")
        engine, pokemon, trainer, skill, choices = self._feature_binding(contestant, feature_sponsor)
        CONTEST_FEATURES.coordinator(engine, trainer)
        key = (engine, trainer.spec["id"])
        if key in self._coordinator_used:
            raise ValueError("Coordinator was already used once in this contest")
        return key

    @staticmethod
    def _stage_feature_cost(engine, trainer, amount, source):
        # A Free Action mutates only the trainer's action history/limited-action
        # flag; AP mutates spec. Stage these native fields with the Appeal roll.
        native = copy(engine)
        native.log_lines = []
        actor = copy(trainer)
        actor.spec = deepcopy(trainer.spec)
        actor._action_history = deepcopy(getattr(trainer, "_action_history", []))
        if getattr(native, "_active_turn_actor", None) is trainer:
            native._active_turn_actor = actor
        if AP.available(actor) < amount:
            raise ValueError("Native trainer cannot pay the contest feature's AP")
        CONTEST_FEATURES.trigger_free_action(native, actor, source)
        AP.spend(actor, amount)
        return actor.spec, actor._action_history, getattr(actor, "_restricted_action_taken", False), native.log_lines

    def perform(self, c, move_name, contest_type, adjacent, center, spend_stat_dice=0,
                reroll_ok=False, fixed_rolls=None, *, reroll_decision=None, flourish_decision=None,
                fashion_decision=None, fashion_instance_id=None, reliable_performance=False, attempt_id=None,
                feature_sponsor=None, style_ranked=None, style_effect=None, voice_lessons=True,
                spend_intro_dice=0, adaptable=None):
        import observed_resolution as OBS
        import coordinator as COORD
        if COORD.contest_skip(self,c):return
        adaptable_plan=None
        requested_move=self.r.move(move_name)['id']
        if adaptable is not None:
            _,prior=OBS.locate(self._performance_observations,'contest.performance',(c,),attempt_id)
            saved=getattr(self,'_adaptable_plan',None)
            if prior is not None and saved is not None:
                adaptable_plan=saved
                if list(adaptable_plan['moves']) != [self.r.move(m)['id'] for m in adaptable]:raise ValueError('observed Adaptable constituents are locked')
            else:
                adaptable_plan=COORD.adaptable_plan(self,c,adaptable)
                self._stage_feature_cost(adaptable_plan['engine'],adaptable_plan['trainer'],0,COORD.ADAPTABLE)
                self._adaptable_plan=adaptable_plan
            move_name=adaptable_plan['move_id']
        COORD.contest_preflight(self,c,self.r.move(move_name)['id'])
        if (type(spend_intro_dice) is not int or type(spend_stat_dice) is not int
                or not 0 <= spend_intro_dice <= spend_stat_dice):
            raise ValueError("Introduction dice must select part of the total stat-die spend")
        if type(voice_lessons) is not bool:raise ValueError('Voice Lessons Contest choice must be boolean')
        performance_binding=self._native_intro_bindings.get(c)
        import style_expert as STYLE
        self._refresh_native_style_dice(c)
        if type(reliable_performance) is not bool:
            raise ValueError("Reliable Performance selection must be boolean")
        if reliable_performance and (fixed_rolls is not None or reroll_ok or reroll_decision is not None or flourish_decision is not None or fashion_decision is not None):
            raise ValueError("Reliable Performance replaces the roll and cannot combine with rolled faces or rerolls")
        if sum(value is not None for value in (reroll_decision,flourish_decision,fashion_decision)) > 1:
            raise UnresolvedRuleSelection("contest/reroll-order", ["multiple_feature_reroll_order_required"])
        if fashion_instance_id is not None and fashion_decision is None:
            raise ValueError("fashion_instance_id requires an explicit Fashion decision")
        if feature_sponsor is not None:
            if fashion_decision is not None or not (reroll_decision is not None or flourish_decision is not None or reliable_performance):
                raise ValueError("feature sponsor requires a Coordinator or Style performance feature")
            self._feature_binding(c, feature_sponsor)
        key,observed=OBS.locate(self._performance_observations,'contest.performance',(c,),attempt_id)
        style_plan=STYLE.contest_plan(self,c,move_name,style_ranked,style_effect,observed)
        kind=('coordinator' if reroll_decision is not None else 'flourish' if flourish_decision is not None
              else 'fashion' if fashion_decision is not None else None)
        declaration={'move':self.r.move(move_name)['id'],'contest_type':contest_type,'adjacent':tuple(adjacent),'center':center,'spend_stat_dice':spend_stat_dice,'fixed_rolls':None if fixed_rolls is None else tuple(fixed_rolls),'feature':kind,'fashion_instance_id':fashion_instance_id,'reliable_performance':reliable_performance}
        declaration['voice_lessons']=voice_lessons
        if adaptable_plan is not None:declaration.update(requested_move=requested_move,adaptable=tuple(adaptable_plan['moves']))
        if spend_intro_dice:declaration['spend_intro_dice']=spend_intro_dice
        if style_ranked is not None or style_effect is not None:declaration.update(style_ranked=style_ranked,style_effect=style_effect)
        if feature_sponsor is not None:declaration['feature_sponsor']=feature_sponsor
        if observed is not None:OBS.verify(observed,declaration)
        if reroll_ok or reroll_decision is not None:
            self.r.selection.require_supported_version("class/코디네이터")
            if reroll_ok or not callable(reroll_decision):
                raise ValueError("Coordinator needs an explicit decision after seeing the first roll")
            if observed is None:coordinator=self._coordinator_owner(c, feature_sponsor)
            else:coordinator=observed['observation']['coordinator']
        else:coordinator=None
        flourish=None
        binding=self._feature_binding(c, feature_sponsor) if coordinator is not None or flourish_decision is not None or fashion_decision is not None or reliable_performance or style_plan else None
        if flourish_decision is not None:
            if not callable(flourish_decision):raise ValueError("Flourish requires an explicit optional decision")
            self.r.selection.require_supported_version(CONTEST_FEATURES.FLOURISH)
            engine,pokemon,trainer,_,_=binding
            stat,_=self.r.move_contest(move_name)
            if observed is None:
                source,chosen=CONTEST_FEATURES.flourish(engine,trainer,pokemon,stat)
                dependencies={CONTEST_FEATURES.STYLE,source}
                for uid in ("class/코디네이터","edge/우아함"):
                    if CONTEST_FEATURES.owned(trainer,uid):dependencies.add(uid)
                for uid,_,children in CONTEST_FEATURES.RANKED.values():
                    dependencies.update(item for item in (uid,*children) if CONTEST_FEATURES.owned(trainer,item))
                for uid in dependencies:self.r.selection.require_supported_version(uid)
                flourish=(engine,trainer.spec['id'],source,chosen)
                if flourish in self._flourish_used:raise ValueError("This Style Flourish branch was already used in this contest")
            else:flourish=observed['observation']['flourish']
        fashion=None
        if fashion_decision is not None:
            if not callable(fashion_decision):raise ValueError("Fashion requires an explicit optional decision")
            import fashion_items as FASHION
            engine,pokemon,_,_,_=binding
            stat,_=self.r.move_contest(move_name)
            if observed is None:fashion,_=FASHION.contest_plan(engine,pokemon,stat,self._fashion_used,instance_id=fashion_instance_id)
            else:fashion=observed['observation']['fashion']
        if reliable_performance:
            for uid in (CONTEST_FEATURES.RELIABLE,CONTEST_FEATURES.NUANCED,"class/코디네이터","edge/우아함"):
                self.r.selection.require_supported_version(uid)
            CONTEST_FEATURES.reliable(binding[0],binding[2],binding[1])
        costs={"flourish":(1,CONTEST_FEATURES.FLOURISH),"coordinator":(0,"class/코디네이터"),"reliable":(2,CONTEST_FEATURES.RELIABLE)}
        def commit_cost(cost):
            if cost is not None:
                engine,_,trainer,_,_=binding
                trainer.spec.clear();trainer.spec.update(cost[0]);trainer._action_history=cost[1];trainer._restricted_action_taken=cost[2];engine.log_lines.extend(cost[3])
        if kind is None:
            # No public callback: the entire private calculation may remain atomic.
            def resolve(actors,rng):
                staged=copy(self);staged.rng,staged.log_lines=rng,[]
                used=staged._perform(actors[0],move_name,contest_type,actors[1:],center,spend_stat_dice,False,fixed_rolls,reliable_performance=reliable_performance,style_ranked=style_ranked,style_effect=style_effect,voice_lessons=voice_lessons,_native_binding=performance_binding,spend_intro_dice=spend_intro_dice)
                cost=STYLE.contest_cost(staged,style_plan,costs.get(used)) if style_plan else (staged._stage_feature_cost(binding[0],binding[2],*costs[used]) if used else None)
                return staged.log_lines,cost
            logs,cost=resolve_transaction([c,*adjacent],self.rng,resolve);self.log_lines.extend(logs);commit_cost(cost)
            if style_plan and style_plan['key'] is not None:self._flourish_used.add(style_plan['key'])
            COORD.contest_commit(self,c,adaptable_plan)
            return
        if observed is None:
            # Validate known feature permission before any speculative public roll.
            if kind in costs:self._stage_feature_cost(binding[0],binding[2],*costs[kind])
            def first_roll(actors,rng):
                staged=copy(self);staged.rng,staged.log_lines=rng,[]
                frame=staged._perform(actors[0],move_name,contest_type,actors[1:],center,spend_stat_dice,False,fixed_rolls,observe_only=True,style_ranked=style_ranked,style_effect=style_effect,voice_lessons=voice_lessons,_native_binding=performance_binding,spend_intro_dice=spend_intro_dice)
                return staged.log_lines,frame,STYLE.contest_cost(staged,style_plan,None)
            logs,frame,style_cost=resolve_transaction([c,*adjacent],self.rng,first_roll)
            commit_cost(style_cost)
            if style_plan and style_plan['key'] is not None:self._flourish_used.add(style_plan['key'])
            self.log_lines.extend(logs)
            COORD.contest_commit(self,c,adaptable_plan)
            if frame is None:return
            # Stat dice, move choice, pre-roll effects and RNG are now committed.
            references=tuple(adjacent)+(() if feature_sponsor is None else (feature_sponsor,))
            observed=OBS.begin(self._performance_observations,key,'contest.performance',(c,),declaration,{'frame':frame,'coordinator':coordinator,'flourish':flourish,'fashion':fashion},references=references)
        frame=observed['observation']['frame']
        preview={'attempt_id':key,'move_id':frame['move_id'],'rolls':tuple(frame['rolls']),'center':frame['center']}
        if kind=='coordinator':
            preview.update(appeal=frame['appeal']+frame['eff'].get('per_6',{}).get('appeal',0)*frame['rolls'].count(6),fumble=frame['fumble']+frame['eff'].get('per_1',{}).get('fumble',0)*frame['rolls'].count(1))
        else:preview['ones']=frame['rolls'].count(1)
        callback=reroll_decision if kind=='coordinator' else flourish_decision if kind=='flourish' else fashion_decision
        chosen=OBS.decide(observed,callback,preview) if frame['total']>0 else False
        if chosen:
            binding=self._feature_binding(c, feature_sponsor)
            # Eligibility can change while the UI is waiting; decline still keeps
            # the original outcome even if a reroll is no longer available.
            if kind=='coordinator':self._coordinator_owner(c, feature_sponsor)
            elif kind=='flourish':
                CONTEST_FEATURES.flourish(binding[0],binding[2],binding[1],self.r.move_contest(move_name)[0])
                if flourish in self._flourish_used:raise ValueError('This Style Flourish branch was already used in this contest')
            else:
                import fashion_items as FASHION
                current,_=FASHION.contest_plan(binding[0],binding[1],self.r.move_contest(move_name)[0],self._fashion_used,instance_id=fashion_instance_id)
                if current!=fashion:raise ValueError('Fashion contest physical source changed after observation')
        def finish(actors,rng):
            staged=copy(self);staged.rng,staged.log_lines=rng,[]
            # Charge only a selected reroll; the initial appeal cannot be undone.
            cost=staged._stage_feature_cost(binding[0],binding[2],*costs[kind]) if chosen and kind in costs else None
            used=staged._finish_performance(actors[0],actors[1:],frame,kind if chosen else None)
            return staged.log_lines,used,cost
        logs,used,cost=resolve_transaction([c,*adjacent],self.rng,finish)
        self.log_lines.extend(logs);commit_cost(cost)
        if used=='coordinator':self._coordinator_used.add(coordinator)
        elif used=='flourish':self._flourish_used.add(flourish)
        elif used=='fashion':self._fashion_used.add(fashion)
        OBS.complete(observed,{'attempt_id':key,'rerolled':used or False})

    def _perform(self, c, move_name, contest_type, adjacent, center, spend_stat_dice=0, reroll_ok=False, fixed_rolls=None, *, reliable_performance=False, observe_only=False,style_ranked=None,style_effect=None,voice_lessons=True,_native_binding=None,spend_intro_dice=0):
        if len({id(a) for a in adjacent}) != len(adjacent) or any(a is c for a in adjacent):
            raise ValueError("Adjacent contestants must be distinct other actors")
        if any(type(a.excitement) is not int or not 0 <= a.excitement <= 5 for a in [c, *adjacent]):
            raise ValueError("Contest excitement must be an integer from 0 to 5")
        selected_move = self.r.move(move_name)
        stat, eff_name = self.r.move_contest(selected_move["id"])
        rules = self.r.performance_rules()
        eff = rules["effects"][eff_name]
        # Resolve learned and saved identities through the same selected profile.
        learned = {self.r.move(move)["id"] for move in c.moves}
        mixed=__import__('coordinator').contest_preflight(self,c,selected_move['id'])
        if selected_move["id"] not in learned and style_ranked is None and mixed is None:
            raise ValueError(f"{c.name} has not learned {selected_move['name']}")
        last_id = self.r.move(c.last_move)["id"] if c.last_move else None
        repeated = last_id == selected_move["id"]
        if repeated and rules["performance-stage"]["no_repeat_consecutive_move"] and not eff.get("may_repeat", False):
            raise ValueError("Consecutive use requires an explicit repeat exception")
        if type(spend_stat_dice) is not int or spend_stat_dice < 0:
            raise ValueError("Stat dice spending must be a non-negative integer")
        if spend_stat_dice > rules["stat-dice"]["max_spend_per_move"]:
            raise ValueError("Stat dice spending exceeds the per-move limit")
        if type(spend_intro_dice) is not int or not 0 <= spend_intro_dice <= spend_stat_dice:
            raise ValueError("Introduction dice must select part of the total stat-die spend")
        intro_pool = getattr(c, '_intro_stat_dice', {})
        if spend_intro_dice > intro_pool.get(stat, 0):
            raise ValueError("Not enough remaining shared introduction dice")
        if spend_stat_dice - spend_intro_dice > c.stat_dice.get(stat, 0):
            raise ValueError("Not enough remaining contest stat dice")
        if fixed_rolls is not None:
            self.validate_d6(fixed_rolls)
        move_name = selected_move["name"]
        c.last_move = selected_move["id"]
        ex_start = c.excitement
        self.log(f"  {c.name} {move_name} ({stat} / {eff_name}){' [관심의 중심]' if center else ''}", "contest/effects")
        # 효과에 따른 흥분도 변화와 주사위 수
        base = eff["dice"]
        if base == "5 - self_excitement":
            n = 5 - c.excitement
        elif base == "self_excitement":
            n = c.excitement
        elif base == "2 * self_excitement":
            lost = c.excitement
            c.excitement = 0
            self.log(f"    흥분도 {lost} → 0, 잃은 1점당 +2d6", "contest/effects")
            n = 2 * lost
        elif base == "sum(adjacent_excitement) - self_excitement_after_loss":
            self.clamp_ex(c, -2)
            n = sum(a.excitement for a in adjacent) - c.excitement
        else:
            n = int(base)
        # Double Time contributes a signed count; add turn-start Voltage before
        # determining the final pool. Clamping this component changes the rule.
        if eff.get("if") == "self_excitement >= 2" and c.excitement >= 2:
            n += eff["then"]["bonus_dice"]
        if eff.get("if") == "all_adjacent_excitement_greater" and adjacent and all(a.excitement > c.excitement for a in adjacent):
            n += eff["then"]["bonus_dice"]; self.clamp_ex(c, eff["then"]["self_excitement"])
        if eff.get("if") == "all_adjacent_excitement_lower" and adjacent and all(a.excitement < c.excitement for a in adjacent):
            n += eff["then"]["bonus_dice"]; self.clamp_ex(c, eff["then"]["self_excitement"])
        if eff.get("if") == "same_move_as_last_turn" and repeated:
            n += eff["then"]["bonus_dice"]; self.clamp_ex(c, eff["then"]["self_excitement"])
        if eff.get("if") == "move_type_matches_contest" and stat == contest_type:
            self.clamp_ex(c, eff["then"]["self_excitement"])
            for a in adjacent:
                self.clamp_ex(a, eff["then"]["adjacent_excitement"])
        doubled = c.double_next
        if doubled:
            n *= 2; c.double_next = False
            self.log("    준비하기: 기술 주사위 두 배", "contest/effects")
        if isinstance(eff.get("self_excitement"), int) and eff_name not in ("더블 타임",):
            self.clamp_ex(c, eff["self_excitement"])
        if isinstance(eff.get("adjacent_excitement"), int):
            lost_total = 0
            for a in adjacent:
                lost_total += abs(self.clamp_ex(a, eff["adjacent_excitement"])) if eff["adjacent_excitement"] < 0 else self.clamp_ex(a, eff["adjacent_excitement"])
            if eff.get("self_excitement") == "+amount_lost_by_adjacent":
                self.clamp_ex(c, lost_total)
        if eff.get("next_round") == "double_move_dice":
            c.double_next = True
        if "lose_fumble" in eff:
            lost = min(c.fumble, ex_start)
            c.fumble -= lost
            self.log(f"    은총: 펌블 -{lost}", "contest/effects")
            if lost <= 2:
                self.clamp_ex(c, 1)
            c.immune_fumble = True
        # 보너스 주사위: 흥분도(턴 시작), 타입 일치, 스탯 주사위
        tmod, why = self.type_mod(stat, contest_type)
        if style_effect is not None:
            matching=self.type_mod(contest_type,contest_type)[0]
            tmod=min(matching,tmod+matching);why+=' / Style alignment'
        if doubled:
            tmod *= 2  # The source calls both type adjustments part of the Move's dice.
        spend = spend_stat_dice
        c.stat_dice[stat] = c.stat_dice.get(stat, 0) - spend + spend_intro_dice
        if spend_intro_dice:
            intro_pool[stat] -= spend_intro_dice
        voice=0
        binding=_native_binding if _native_binding is not None else self._native_intro_bindings.get(c)
        if voice_lessons and binding is not None:
            native,pokemon,trainer,_,_=binding
            __import__('world_entities').require_actors(native,pokemon,trainer)
            voice=__import__('musician').contest_bonus(native,pokemon,trainer,selected_move)
        total = n + ex_start + tmod + spend + voice
        if fixed_rolls is not None:
            self.validate_d6(fixed_rolls, max(0, total))
        if total <= 0 and tmod < 0:
            c.fumble += 1
            self.log("    굴릴 주사위 없음(대항) → 펌블 +1", "contest/type-match")
            return
        override = eff.get("scoring_override")
        if reliable_performance and total > 0:
            rolls, appeal, fumble = [], total, 0
            rerolled = "reliable"
            self.log(f"    신뢰의 공연: 굴릴 주사위 {total}개 → 어필 {total} (실제 눈 없음)", CONTEST_FEATURES.RELIABLE)
        else:
            rolls = fixed_rolls if fixed_rolls is not None else self.d6(total)
            self.log(f"    주사위 {n}(효과) + {ex_start}(흥분도) {tmod:+d}({why}) + {spend}({stat} 스탯) = {total}d6 → {rolls}", "contest/type-match")
            appeal, fumble = self.score(rolls, center, override)
            rerolled = False
        frame={'pool_components':{'move':n,'turn_start_excitement':ex_start,'type_match':tmod,'spent_stat':spend},'move_id':selected_move['id'],'total':total,'rolls':tuple(rolls),'appeal':appeal,'fumble':fumble,'eff':deepcopy(eff),'center':center,'rerolled':rerolled}
        if voice:frame['pool_components']['voice_lessons']=voice
        if observe_only:return frame
        return self._finish_performance(c,adjacent,frame)

    def _finish_performance(self,c,adjacent,frame,reroll_kind=None):
        """Private final calculation. No callback may observe this transaction."""
        total=frame['total'];rolls=list(frame['rolls']);appeal=frame['appeal'];fumble=frame['fumble'];eff=frame['eff'];center=frame['center'];rerolled=frame['rerolled']
        override=eff.get('scoring_override')
        if reroll_kind=='coordinator' and total>0:
            rolls=self.d6(total);appeal,fumble=self.score(rolls,center,override);rerolled='coordinator'
            self.log(f"    코디네이터 재굴림 → {rolls} ({appeal} 어필)","class/코디네이터")
        if reroll_kind=='flourish' and total>0:
            import roll_pools as POOLS
            selection=POOLS.select(rolls,operation='reroll',indices=[i for i,face in enumerate(rolls) if face==1],rng=self.rng)
            rolls=list(selection['faces'])
            appeal,fumble=self.score(rolls,center,override);rerolled='flourish'
            self.log(f"    스타일 플로리시: 1만 한 번 재굴림 → {rolls}",CONTEST_FEATURES.FLOURISH)
        if reroll_kind=='fashion' and total>0:
            import roll_pools as POOLS
            selection=POOLS.select(rolls,operation='reroll',indices=[i for i,face in enumerate(rolls) if face==1],rng=self.rng)
            rolls=list(selection['faces'])
            appeal,fumble=self.score(rolls,center,override);rerolled='fashion'
            self.log(f"    패션: 1이 나온 주사위 재굴림 → {rolls}","item/fashion")
        if eff.get("per_6", {}).get("appeal"):
            appeal += eff["per_6"]["appeal"] * rolls.count(6)
        if eff.get("per_1", {}).get("fumble"):
            fumble += eff["per_1"]["fumble"] * rolls.count(1)
        if eff.get("per_6", {}).get("self_excitement"):
            self.clamp_ex(c, eff["per_6"]["self_excitement"] * rolls.count(6))
        if eff.get("per_6", {}).get("adjacent_fumble"):
            for a in adjacent:
                if not a.immune_fumble:
                    a.fumble += eff["per_6"]["adjacent_fumble"] * rolls.count(6)
        if eff.get("score_mode") == "fumble_to_adjacent":
            for a in adjacent:
                if not a.immune_fumble:
                    a.fumble += appeal
                    self.log(f"    방해: {a.name} 펌블 +{appeal}", "contest/effects")
            appeal = 0
        c.appeal += appeal
        c.fumble += fumble
        self.log(f"    어필 +{appeal}{f', 펌블 +{fumble}' if fumble else ''} → {c.name} 어필 {c.appeal} 펌블 {c.fumble} 흥분도 {c.excitement}", "contest/appeal-scoring")
        return rerolled

    def _perform_choice(self, actor, round_type, adjacent, center, declaration):
        # An optional third item is a decision callback invoked after the first roll.
        if not isinstance(declaration, (list, tuple)) or len(declaration) not in (2, 3):
            raise ValueError("Choose a Move, stat dice, and optionally a reroll decision")
        move, spend = declaration[:2]
        options = {}
        if len(declaration) == 3:
            options = declaration[2] if isinstance(declaration[2], dict) else {"reroll_decision": declaration[2]}
            if set(options) - {"reroll_decision", "flourish_decision", "fashion_decision", "fashion_instance_id", "reliable_performance", "style_ranked", "style_effect", "adaptable", "spend_intro_dice"}:
                raise ValueError("Unsupported contest feature choice")
        self.perform(actor, move, round_type, adjacent, center, spend_stat_dice=spend, **options)

    def trainer_participant(self, pokemon_contestant):
        """Use the bound trainer's actual learned Moves in an optional paired mode."""
        binding = self._native_intro_bindings.get(pokemon_contestant)
        if binding is None:
            raise ValueError("Trainer participation requires native trainer/Pokemon ownership")
        if pokemon_contestant in self._trainer_partners:
            return self._trainer_partners[pokemon_contestant]
        engine, pokemon, trainer, skill, choices = binding
        self._native_intro_state(binding)
        partner = Contestant(trainer.name, pokemon_contestant.stat_dice, [mid for mid in trainer.moves if mid!="struggle"],
                             skill, pokemon_contestant.intro_rank_dice,
                             pokemon_contestant.intro_stat)
        # Both perform() transactions retain dictionary identity when committing.
        partner.stat_dice = pokemon_contestant.stat_dice
        self._trainer_partners[pokemon_contestant] = partner
        return partner

    TRAINER_SOURCE='ch08-contests/비전통적인-콘테스트-형식/트레이너-참가-콘테스트'

    def _validate_pair_binding(self,binding):
        engine,pokemon,trainer,_,_=binding
        for rules in (self.r,engine.r):
            if rules._selected_rule(self.TRAINER_SOURCE)!=self.TRAINER_SOURCE:
                raise ValueError('selected trainer-participation source required')
        return self._validate_native_binding(binding)

    def _validate_native_binding(self,binding):
        """Actual owner, registration and availability shared by native formats."""
        import pokemon_party as PARTY
        engine,pokemon,trainer,_,_=binding
        CONTEST_FEATURES.owner(trainer,pokemon)
        roster=[*getattr(engine,'everyone',[]),*getattr(engine,'_time_actors',[]),*getattr(engine.gm,'everyone',[])]
        for actor in (trainer,pokemon):
            uid=actor.spec.get('id')
            matches={id(a):a for a in roster if a.spec.get('id')==uid}
            if not uid or actor.r is not engine.r or len(matches)!=1 or next(iter(matches.values())) is not actor:
                raise ValueError('actual unique registered contest participant required')
            if actor.dead or actor.fainted or '잠듦' in actor.conditions or getattr(actor,'captured',False) or getattr(actor,'on_field',True) is False:
                raise ValueError('actual conscious available contest participant required')
        PARTY.require_participation(engine,pokemon)
        return binding

    def configure_trainer_interactions(self,*,reason,double_next_from=None,attention_transfer=None):
        """Explicit GM options from ch08:281, not ordinary Contest Effect rewrites.

        Korean names Seen Nothing Yet; original PTU p269 names Get Ready,
        consistent with its next-round doubling effect. Keep the GM's explicit
        source choice and reason (including a Korean-literal table ruling).
        Attention transfer's unspecified quantity is likewise a GM decision.
        """
        if self._paired_run is not None:raise ValueError('choose participant interactions before starting the contest')
        if not isinstance(reason,str) or not reason.strip():raise ValueError('GM interaction reason required')
        if double_next_from not in (None,'준비하기','이제부터'):raise ValueError('explicit source of optional next-partner doubling required')
        if attention_transfer is not None and (type(attention_transfer) is not int or not 1<=attention_transfer<=5):raise ValueError('GM Attention Grabber transfer quantity must be 1..5')
        engines={binding[0] for binding in self._native_intro_bindings.values()}
        if len(engines)!=1:raise ValueError('one actual native contest required for GM interaction policy')
        engine=next(iter(engines))
        for binding in self._native_intro_bindings.values():self._validate_pair_binding(binding)
        if self._trainer_interactions is not None:raise ValueError('participant interaction policy already recorded')
        record={'source':self.TRAINER_SOURCE,'double_next_from':double_next_from,'attention_transfer':attention_transfer,'reason':reason,'authority':'table_ruling'}
        self._trainer_interactions=record
        engine.gm._rec('트레이너 참가 상호작용 재정',None,record,reason)
        return deepcopy(record)

    def snapshot(self,name='contest'):
        """Explicit GM checkpoint of the contest and its real feature payers."""
        if self._paired_busy or self._standard_busy or getattr(self,'_festival_busy',False):raise ValueError('cannot checkpoint inside an executing contest callback')
        if not isinstance(name,str) or not name:raise ValueError('checkpoint identity required')
        actors=set(self._native_intro_bindings)|set(self._trainer_partners.values())
        if getattr(self,'_festival_run',None) is not None:
            actors.update(self._festival_run['contract'][0])
        if self._standard_run is not None:
            actors.update(self._standard_run['contract'][0])
            rotation=self._standard_run.get('rotation')
            if rotation is not None:
                actors.update(member for team in rotation['teams'] for member in team)
        natives={binding[0] for binding in self._native_intro_bindings.values()}
        pins={id(self):self,id(self.r):self.r,**{id(c):c for c in actors}}
        for native in natives:
            pins.update({id(native):native,id(native.r):native.r})
            for binding in self._native_intro_bindings.values():
                pins.update({id(binding[1]):binding[1],id(binding[2]):binding[2]})
        fields=('_native_intro_bindings','_trainer_partners','_flourish_used','_fashion_used','_performance_observations','_coordinator_used','_adaptable_uses','_adaptable_plan','_paired_run','_standard_run','_festival_run','_trainer_interactions','log_lines','last_standings')
        state={'actors':{c:vars(c) for c in actors},'engine':{k:getattr(self,k) for k in fields if hasattr(self,k)},'rng':self.rng}
        copied=deepcopy(state,dict(pins))
        native_names={native:'contest:'+str(id(self))+':'+name for native in natives}
        for native,key in native_names.items():native.gm.snapshot(key)
        self._snapshots[name]=(copied,pins,native_names)
        return name

    def restore(self,name='contest',*,reason):
        if self._paired_busy or self._standard_busy or getattr(self,'_festival_busy',False):raise ValueError('cannot restore inside an executing contest callback')
        if not isinstance(reason,str) or not reason.strip():raise ValueError('explicit GM restore reason required')
        saved,pins,native_names=self._snapshots[name]
        state=deepcopy(saved,dict(pins))
        for native,key in native_names.items():native.gm.restore(key,reason=reason)
        for actor,value in state['actors'].items():object.__setattr__(actor,'__dict__',value)
        for k,value in state['engine'].items():setattr(self,k,value)
        if 'last_standings' not in state['engine']:self.__dict__.pop('last_standings',None)
        self.rng=state['rng']
        self.log('[GM contest restore] '+reason,self.TRAINER_SOURCE)

    def _paired_declaration(self,value):
        if not isinstance(value,(list,tuple)) or len(value) not in (2,3):raise ValueError('choose a learned Move, stat dice and optional feature choices')
        move,spend=value[:2]
        options={} if len(value)==2 else (dict(value[2]) if isinstance(value[2],dict) else {'reroll_decision':value[2]})
        if set(options)-{'reroll_decision','flourish_decision','fashion_decision','fashion_instance_id','reliable_performance','pair_interaction','feature_sponsor','style_ranked','style_effect','adaptable','spend_intro_dice'}:raise ValueError('unsupported participant performance choice')
        interaction=options.pop('pair_interaction',False)
        if type(interaction) is not bool:raise ValueError('optional pair interaction must be boolean')
        locked={k:v for k,v in options.items() if k not in ('reroll_decision','flourish_decision','fashion_decision')}
        locked.update(move=self.r.move(move)['id'],spend=spend,feature='flourish' if 'flourish_decision' in options else 'coordinator' if 'reroll_decision' in options else 'fashion' if 'fashion_decision' in options else None,pair_interaction=interaction)
        return move,spend,options,locked

    def _paired_interaction(self,state,owner,actor,move,selected,*,commit=False):
        if not selected:return
        policy=self._trainer_interactions
        if state['model']!='simultaneous' or not policy:raise ValueError('this interaction requires an explicit simultaneous-mode GM policy')
        partner=state['pairs'][owner]
        if actor is not partner:raise ValueError('source example transfers from the trainer to its own Pokemon')
        _,effect=self.r.move_contest(move)
        order=state['selections'][owner]
        if effect==policy['double_next_from']:
            if order.index(owner)<order.index(partner):raise ValueError('Pokemon must still have its same-round performance')
            if commit:
                owner.double_next=True
                if effect=='준비하기':partner.double_next=False
        elif effect=='주목 끌기' and policy['attention_transfer'] is not None:
            if commit:
                amount=min(policy['attention_transfer'],partner.excitement,5-owner.excitement)
                self.clamp_ex(partner,-amount);self.clamp_ex(owner,amount)
        else:raise ValueError('selected Move has no approved optional pair interaction')
        if commit:self.log('[GM participant interaction] '+effect+': '+policy['reason'],self.TRAINER_SOURCE)

    def _run_trainer_participants(self, contestants, contest_type, chooser, *,
                                  variant, model, order_chooser, contest_id=None):
        if self._paired_busy:raise ValueError('contest callback cannot reenter its own contest')
        if model not in ('simultaneous','alternating'):raise ValueError('choose simultaneous or alternating trainer participation')
        if not callable(order_chooser) or not callable(chooser):raise ValueError('explicit performance and participant order providers required')
        if contest_id is not None and (not isinstance(contest_id,str) or not contest_id):raise ValueError('contest identity required')
        if variant not in ('standard','super'):raise UnresolvedRuleSelection('contest/variant',['paired_festival_not_resolved'])
        if (variant=='super' and contest_type is not None) or (variant=='standard' and contest_type not in self.r.mech('contest/type-match')['ring']):raise ValueError('contest type does not match selected variant')
        self.r.performance_rules();self.r._selected_rule(self.TRAINER_SOURCE)
        if not 3<=len(contestants)<=5 or len(set(contestants))!=len(contestants):raise ValueError('three to five distinct competitor pairs required')
        pairs={};native_ids=set();native_engines=set()
        for c in contestants:
            if c not in self._trainer_partners:raise ValueError('each participant needs its bound native trainer partner')
            binding=self._validate_pair_binding(self._native_intro_bindings[c]);native_engines.add(binding[0])
            for actual in binding[1:3]:
                uid=actual.spec['id']
                if uid in native_ids:raise ValueError('native performer cannot occupy two competitor pairs')
                native_ids.add(uid)
            partner=self._trainer_partners[c]
            if partner.stat_dice is not c.stat_dice:raise ValueError('participants must share one actual stat pool')
            for actor,actual in ((c,binding[1]),(partner,binding[2])):
                if {self.r.move(m)['id'] for m in actor.moves}!={self.r.move(m)['id'] for m in actual.moves}:raise ValueError('actual learned Moves changed; original declaration cannot be replaced')
                for move in actor.moves:self.r.move_contest(move)
            pairs[c]=partner
        if len(native_engines)!=1:raise ValueError('one actual native contest context required')
        HALLS.native_context(self, contestants)
        contract=(tuple(contestants),contest_type,variant,model,deepcopy(self._trainer_interactions))
        state=self._paired_run
        if state is not None:
            if state['contract']!=contract or contest_id not in (None,state['id']):raise ValueError('resume the same contest and original participants/model')
            if state['phase']=='complete':raise ValueError('contest already completed; no duplicate rewards or performances')
        else:
            table=self.r.mech('contest/position-tables')[str(len(contestants))]
            state={'id':contest_id or 'trainer-contest:'+str(uuid.uuid4()),'contract':contract,'phase':'intro','pairs':pairs,'table':table,'round':0,'selections':{},'previous':{},'slot':0,'performer':0,'pending':None,'model':model,'round_type':None}
            self._paired_run=state
        self._paired_busy=True
        try:
            if state['phase']=='intro':
                self.intro_stage(contestants,contest_type)
                for c,partner in pairs.items():
                    partner.letter=c.letter
                    if model=='alternating':
                        shared={'excitement':c.excitement,'double_next':c.double_next,'immune_fumble':c.immune_fumble}
                        c._paired_state=partner._paired_state=shared
                state['phase']='round'
            by_letter={c.letter:c for c in contestants};table=state['table']
            while state['round']<len(table['rounds']):
                rnd=state['round']+1;row=table['rounds'][state['round']]
                if state['round_type'] is None:state['round_type']=self.random_contest_type() if variant=='super' else contest_type
                for c in contestants:
                    if c in state['selections']:continue
                    chosen=order_chooser(c,pairs[c],rnd)
                    if not isinstance(chosen,(list,tuple)):raise ValueError('performer order must identify actual actors')
                    if model=='simultaneous':
                        if len(chosen)!=2 or set(chosen)!={c,pairs[c]}:raise ValueError('both partners perform once in the chosen order')
                    elif len(chosen)!=1 or chosen[0] not in (c,pairs[c]) or state['previous'].get(c) is chosen[0]:raise ValueError('alternating partners must take turns')
                    state['selections'][c]=tuple(chosen)
                if state['phase']=='round':
                    for c,partner in pairs.items():c.immune_fumble=partner.immune_fumble=False
                    self.log('## 트레이너 참가 라운드 '+str(rnd)+': '+model+', '+state['round_type'],self.TRAINER_SOURCE)
                    state['phase']='perform'
                columns=sorted(range(len(row)),key=lambda i:table['turn_order_by_column'][i])
                while state['slot']<len(columns):
                    i=columns[state['slot']];owner=by_letter[row[i]]
                    neighboring=[by_letter[row[j]] for j in (i-1,i+1) if 0<=j<len(row)]
                    adjacent=[a for other in neighboring for a in state['selections'][other]]
                    order=state['selections'][owner];center=table['turn_order_by_column'][i]==1
                    while state['performer']<len(order):
                        actor=order[state['performer']]
                        self._validate_pair_binding(self._native_intro_bindings[owner])
                        value=chooser(actor,rnd,adjacent,center)
                        binding=self._validate_pair_binding(self._native_intro_bindings[owner])
                        for declared,actual in ((owner,binding[1]),(pairs[owner],binding[2])):
                            if {self.r.move(m)['id'] for m in declared.moves}!={self.r.move(m)['id'] for m in actual.moves}:
                                raise ValueError('actual learned Moves changed during the performance choice')
                        move,spend,options,locked=self._paired_declaration(value)
                        pending=state['pending']
                        if pending is not None and pending!=locked:raise ValueError('observed performance choice is locked; change only its decision response')
                        self._paired_interaction(state,owner,actor,move,locked['pair_interaction'])
                        attempt=state['id']+':'+str(rnd)+':'+str(i)+':'+str(state['performer'])
                        try:self.perform(actor,move,state['round_type'],adjacent,center,spend_stat_dice=spend,attempt_id=attempt,**options)
                        except Exception:
                            if attempt in self._performance_observations:state['pending']=locked
                            raise
                        if center: actor.been_center=True
                        self._paired_interaction(state,owner,actor,move,locked['pair_interaction'],commit=True)
                        state['pending']=None;state['performer']+=1
                    state['slot']+=1;state['performer']=0
                self._end_contest_round([*contestants,*pairs.values()], final=rnd==len(table['rounds']))
                state['previous']={c:chosen[0] for c,chosen in state['selections'].items()}
                state.update(round=state['round']+1,selections={},slot=0,performer=0,round_type=None,phase='round')
            scores={c:(c.appeal+pairs[c].appeal,c.fumble+pairs[c].fumble) for c in contestants}
            final=sorted(contestants,key=lambda c:-(scores[c][0]-scores[c][1]))
            self.last_standings=[{'name':c.name,'trainer':pairs[c].name,'appeal':scores[c][0],'fumble':scores[c][1],'net':scores[c][0]-scores[c][1]} for c in final]
            state.update(phase='complete',result=tuple(final),
                         terminal_scores=tuple((c,scores[c][0]-scores[c][1]) for c in contestants))
            for result in self.last_standings:self.log(str(result),'contest/appeal-scoring')
            high=self.last_standings[0]['net'];leaders=[r for r in self.last_standings if r['net']==high]
            self.log(('우승: ' if len(leaders)==1 else '최고점 동률 (단독 우승 판정 미확정): ')+', '.join(r['name'] for r in leaders),'contest/performance-stage')
            HALLS.award_contest(self)
            return final
        finally:self._paired_busy=False

    @staticmethod
    def _end_contest_round(actors, *, final):
        """Expire round protection and, at contest end, unused next-round boosts."""
        for actor in actors:
            actor.immune_fumble = False
            if final:
                actor.double_next = False

    def random_contest_type(self):
        """Supercontest: one d6 per round, retry six without consuming a turn."""
        types = ["근사함", "강인함", "아름다움", "슬기로움", "귀여움"]
        face = self.d6(1)[0]
        while face == 6:
            face = self.d6(1)[0]
        return types[face - 1]

    def run_rotation(self, teams, contest_type, chooser, *, representatives,
                     performer_selector=None, orders=None, round_types=None,
                     contest_id=None):
        """Run a rotation contest with one distinct Pokemon per team and round.

        ``orders`` fixes every team's sequence before the contest.  Without it,
        ``performer_selector`` chooses from that team's unused roster at each
        round boundary.  A fixed ``contest_type`` gives the usual format;
        alternatively ``round_types`` records one predeclared stat per round.
        The introduction representative and all performers share excitement
        and next-performance effects, while the occurrence ledger caps the
        team's total spent contest dice at twice the competitor count.
        """
        if getattr(self,'_festival_run',None) is not None:
            raise ValueError("resume the original Festival")
        if self._standard_busy or self._paired_busy:
            raise ValueError("contest callback cannot reenter its own contest")
        if self._paired_run is not None:
            raise ValueError("resume the original paired contest")
        if not callable(chooser):
            raise ValueError("explicit rotation performance choice provider required")
        if contest_id is not None and (not isinstance(contest_id, str) or not contest_id):
            raise ValueError("contest identity required")
        types = tuple(self.r.mech("contest/type-match")["ring"])
        proposed = ROTATION.create(
            teams, representatives, orders=orders, contest_type=contest_type,
            round_types=round_types, valid_types=types)
        ROTATION.validate_native_roster(proposed["teams"], self._native_intro_bindings)
        HALLS.native_context(self, [c for team in proposed['teams'] for c in team])
        anchors = proposed["representatives"]
        variant = "standard" if round_types is None else "super"
        contract = (anchors, contest_type, variant)
        self.r.performance_rules()
        self.r.mech("contest/intro-stage")
        for team in proposed["teams"]:
            for member in team:
                for move in member.moves:
                    self.r.move_contest(move)

        state = self._standard_run
        if state is not None:
            if "rotation" not in state:
                raise ValueError("resume the original standard contest")
            if state["phase"] == "complete":
                raise ValueError("rotation contest already completed; no duplicate performances")
            if (state["contract"] != contract or contest_id not in (None, state["id"])
                    or ROTATION.declaration(state["rotation"]) != ROTATION.declaration(proposed)):
                raise ValueError("resume the same rotation contest, roster, order, and types")
            rotation = state["rotation"]
            ROTATION.validate(rotation, state=state, valid_types=types,
                              move_validator=self.r.move_contest,
                              native_bindings=self._native_intro_bindings)
        else:
            ROTATION.bind_shared_state(proposed)
            table = self.r.mech("contest/position-tables")[str(len(anchors))]
            state = {"id": contest_id or "rotation-contest:"+str(uuid.uuid4()), "contract": contract,
                     "phase": "intro", "table": table, "round": 0, "slot": 0,
                     "round_type": None, "pending": None, "rotation": proposed}
            self._standard_run = state
            rotation = proposed
            ROTATION.validate(rotation, state=state, valid_types=types,
                              move_validator=self.r.move_contest,
                              native_bindings=self._native_intro_bindings)

        self._standard_busy = True
        try:
            if state["phase"] == "intro":
                before_intro = {rep: dict(rep.stat_dice) for rep in anchors}
                self.intro_stage(anchors, contest_type)
                ROTATION.share_introduction(rotation, before_intro)
                self.log("# 로테이션 콘테스트 참가 팀 " + str(len(anchors)),
                         "contest/performance-stage")
                self.log("## 소개 단계: 팀별 대표 " + ", ".join(c.name for c in anchors),
                         "contest/intro-stage")
                state["phase"] = "round"
            by_letter = {c.letter: c for c in anchors}
            table = state["table"]
            while state["round"] < len(table["rounds"]):
                rnd = state["round"] + 1
                row = table["rounds"][state["round"]]
                if state["round_type"] is None:
                    state["round_type"] = rotation["round_types"][state["round"]]
                if state["phase"] == "round":
                    current = ROTATION.select_round(
                        rotation, state["round"], performer_selector)
                    for rep in anchors:
                        rep.immune_fumble = False
                    self.log("## 로테이션 라운드 " + str(rnd) + ": " +
                             ", ".join(rep.name + "=" + current[rep].name for rep in anchors),
                             "contest/performance-stage")
                    self.log("  라운드 유형: " + state["round_type"],
                             "contest/performance-stage")
                    state["phase"] = "perform"
                current = rotation["current"]
                columns = sorted(range(len(row)), key=lambda i: table["turn_order_by_column"][i])
                while state["slot"] < len(columns):
                    column = columns[state["slot"]]
                    representative = by_letter[row[column]]
                    performer = current[representative]
                    neighbors = [by_letter[row[j]] for j in (column - 1, column + 1)
                                 if 0 <= j < len(row)]
                    adjacent = [current[neighbor] for neighbor in neighbors]
                    center = table["turn_order_by_column"][column] == 1
                    original_last = performer.last_move
                    performer.last_move = rotation["last_moves"][representative]
                    attempt = None
                    try:
                        value = chooser(performer, rnd, adjacent, center)
                        move, spend, options, locked = self._paired_declaration(value)
                        if locked["pair_interaction"]:
                            raise ValueError("partner interaction is not a rotation performance choice")
                        if state["pending"] is not None and state["pending"] != locked:
                            raise ValueError("observed rotation choice is locked; change only its decision response")
                        ROTATION.validate_native_roster(rotation["teams"], self._native_intro_bindings)
                        attempt = state["id"] + ":" + str(rnd) + ":" + str(column)
                        ROTATION.ensure_budget(rotation, representative, attempt, spend)
                        self.perform(performer, move, state["round_type"], adjacent, center,
                                     spend_stat_dice=spend, attempt_id=attempt, **options)
                    except Exception:
                        performer.last_move = original_last
                        if attempt is not None and attempt in self._performance_observations:
                            ROTATION.charge(rotation, representative, performer, attempt, spend)
                            state["pending"] = locked
                        raise
                    ROTATION.charge(rotation, representative, performer, attempt, spend)
                    ROTATION.complete_performance(
                        rotation, representative, performer, locked["move"])
                    if center:
                        representative.been_center = True
                        performer.been_center = True
                    state["pending"] = None
                    state["slot"] += 1
                self._end_contest_round(
                    [member for team in rotation["teams"] for member in team],
                    final=rnd == len(table["rounds"]))
                ROTATION.finish_round(rotation)
                state.update(round=state["round"] + 1, slot=0,
                             round_type=None, phase="round")

            totals = ROTATION.scores(rotation)
            final = sorted(anchors, key=lambda c: -(totals[c][0] - totals[c][1]))
            self.last_standings = [
                {"name": c.name,
                 "members": tuple(member.name for member in rotation["teams"][anchors.index(c)]),
                 "appeal": totals[c][0], "fumble": totals[c][1],
                 "net": totals[c][0] - totals[c][1],
                 "spent_stat_dice": rotation["spent"][c]}
                for c in final
            ]
            state.update(phase="complete", result=tuple(final),
                         terminal_scores=tuple((c, totals[c][0]-totals[c][1]) for c in anchors))
            ROTATION.validate(rotation, state=state, valid_types=types,
                              move_validator=self.r.move_contest,
                              native_bindings=self._native_intro_bindings)
            for result in self.last_standings:
                self.log(str(result), "contest/appeal-scoring")
            high = self.last_standings[0]["net"]
            leaders = [row for row in self.last_standings if row["net"] == high]
            self.log(("우승: " if len(leaders) == 1 else
                      "최고점 동률 (단독 우승 판정 미확정): ") +
                     ", ".join(row["name"] for row in leaders),
                     "contest/performance-stage")
            HALLS.award_contest(self)
            return final
        finally:
            self._standard_busy = False

    def experience_quote(self, contestant, *, significance=None):
        import contest_experience as EXPERIENCE
        return EXPERIENCE.quote(self, contestant, significance=significance)

    def award_experience(self, contestant, *, significance=None, stat_choices=None):
        import contest_experience as EXPERIENCE
        return EXPERIENCE.award(self, contestant, significance=significance,
                                stat_choices=stat_choices)

    def run(self, contestants, contest_type, chooser, *, variant="standard",
            trainer_model=None, trainer_order=None, contest_id=None,
            festival_variant="standard", festival_policy=None, festival_decisions=None,
            hall_id=None):
        if hall_id is not None and (variant != 'standard' or trainer_model is not None):
            raise ValueError('fixed-type standard Hall entry required')
        if variant == 'festival':
            if trainer_model is not None or trainer_order is not None:
                raise ValueError('basic Festival admits Pokemon performers only')
            return FESTIVAL.run(self, contestants, contest_type, chooser,
                contest_id=contest_id, base_variant=festival_variant,
                resource_policy=festival_policy,
                decisions={} if festival_decisions is None else festival_decisions)
        if getattr(self,'_festival_run',None) is not None:
            raise ValueError('resume the original Festival')
        if festival_policy is not None or festival_decisions is not None or festival_variant != 'standard':
            raise ValueError('Festival declarations require the Festival variant')
        return self._run_standard(contestants, contest_type, chooser, variant=variant,
            trainer_model=trainer_model, trainer_order=trainer_order, contest_id=contest_id,
            hall_id=hall_id)

    def _run_standard(self, contestants, contest_type, chooser, *, variant="standard",
            trainer_model=None, trainer_order=None, contest_id=None, hall_id=None):
        if trainer_model is not None:
            if self._standard_run is not None:
                raise ValueError("resume the original standard contest")
            return self._run_trainer_participants(contestants, contest_type, chooser,
                variant=variant, model=trainer_model, order_chooser=trainer_order, contest_id=contest_id)
        if self._standard_busy or self._paired_busy:
            raise ValueError("contest callback cannot reenter its own contest")
        if self._paired_run is not None:
            raise ValueError("resume the original paired contest")
        if not callable(chooser):
            raise ValueError("explicit contest choice provider required")
        if contest_id is not None and (not isinstance(contest_id,str) or not contest_id):
            raise ValueError("contest identity required")
        if variant not in ("standard", "super"):
            raise UnresolvedRuleSelection("contest/variant", ["festival_resource_reset_and_elimination_tie_policy_required"])
        if variant == "super" and contest_type is not None:
            raise ValueError("Supercontest has no fixed introduction or performance type")
        if variant == "standard" and contest_type not in self.r.mech("contest/type-match")["ring"]:
            raise ValueError("Standard contest needs a fixed valid type")
        self.r.performance_rules()
        self.r.mech("contest/intro-stage")
        if not 3 <= len(contestants) <= 5 or len(set(contestants)) != len(contestants):
            raise ValueError("three to five distinct contest participants required")
        HALLS.native_context(self, contestants)
        hall = None if hall_id is None else HALLS.admit_hall(self, contestants, contest_type, hall_id)
        table = self.r.mech("contest/position-tables")[str(len(contestants))]
        for c in contestants:
            for move in c.moves:
                self.r.move_contest(move)
        contract=(tuple(contestants),contest_type,variant)
        state=self._standard_run
        if state is not None and "rotation" in state:
            raise ValueError("resume the rotation contest with run_rotation")
        if state is not None and state['phase']=='complete':
            if contract==state['contract'] or any(c.intro_completed or c in state['contract'][0] for c in contestants):
                raise ValueError("contest already completed; no duplicate performances")
            if contest_id==state['id']:
                raise ValueError("new contest requires a new occurrence identity")
            # Existing callers may reuse a host with entirely new participants.
            # Preserve old observation receipts; use a distinct occurrence scope.
            contest_id=contest_id or state['id']+':next'
            self._coordinator_used=set();self._flourish_used=set();self._fashion_used=set();self._adaptable_uses={};self.__dict__.pop('_adaptable_plan',None)
            self.__dict__.pop('last_standings',None)
            state=None
        if state is not None:
            if state['contract']!=contract or contest_id not in (None,state['id']):
                raise ValueError("resume the same contest and original participants/variant")
            if hall is not None and state.get('hall') != hall:
                raise ValueError('resume the original Contest Hall')
            HALLS.validate_hall(self, state)
        else:
            state={'id':contest_id or 'standard-contest:'+str(uuid.uuid4()),'contract':contract,
                   'phase':'intro','table':table,'round':0,'slot':0,
                   'round_type':None,'pending':None}
            if hall is not None:state['hall'] = hall
            self._standard_run=state
        self._standard_busy=True
        try:
            if state['phase']=='intro':
                self.intro_stage(contestants,contest_type)
                self.log(f"# 콘테스트 ({contest_type}) 참가 {len(contestants)}명")
                self.log("## 소개 단계")
                state['phase']='round'
            by_letter={c.letter:c for c in contestants}
            table=state['table']
            center_col=table['turn_order_by_column'].index(1)
            while state['round'] < len(table['rounds']):
                rnd=state['round']+1
                row=table['rounds'][state['round']]
                if state['round_type'] is None:
                    state['round_type']=self.random_contest_type() if variant=='super' else contest_type
                round_type=state['round_type']
                if state['phase']=='round':
                    for actor in contestants:
                        actor.immune_fumble=False
                    self.log(f"  라운드 유형: {round_type}", "contest/performance-stage")
                    self.log(f"## 라운드 {rnd}: 무대 " + " | ".join(f"{by_letter[l].name}" for l in row))
                    state['phase']='perform'
                order=sorted(range(len(row)),key=lambda i:table['turn_order_by_column'][i])
                while state['slot'] < len(order):
                    i=order[state['slot']]
                    c=by_letter[row[i]]
                    adjacent=[by_letter[row[j]] for j in (i-1,i+1) if 0<=j<len(row)]
                    center=i==center_col
                    declaration=chooser(c,rnd,adjacent,center)
                    move,spend,options,locked=self._paired_declaration(declaration)
                    if locked['pair_interaction']:
                        raise ValueError("partner interaction requires a trainer participation model")
                    if state['pending'] is not None and state['pending']!=locked:
                        raise ValueError("observed performance choice is locked; change only its decision response")
                    attempt=state['id']+':'+str(rnd)+':'+str(i)
                    try:
                        self.perform(c,move,round_type,adjacent,center,
                                     spend_stat_dice=spend,attempt_id=attempt,**options)
                    except Exception:
                        if attempt in self._performance_observations:
                            state['pending']=locked
                        raise
                    if center: c.been_center=True
                    state['pending']=None
                    state['slot']+=1
                self.log("상태: " + "; ".join(map(repr,contestants)))
                self._end_contest_round(contestants, final=rnd==len(table['rounds']))
                state.update(round=state['round']+1,slot=0,round_type=None,phase='round')
            final=sorted(contestants,key=lambda c:-(c.appeal-c.fumble))
            self.last_standings=[{'name':c.name,'appeal':c.appeal,'fumble':c.fumble,'net':c.appeal-c.fumble} for c in final]
            state.update(phase='complete',result=tuple(final),
                         terminal_scores=tuple((c,c.appeal-c.fumble) for c in contestants))
            self.log("## 결과")
            for c in final:
                self.log(f"  {c.name}: 어필 {c.appeal} - 펌블 {c.fumble} = {c.appeal-c.fumble}", "contest/appeal-scoring")
            high_score=final[0].appeal-final[0].fumble
            leaders=[c for c in final if c.appeal-c.fumble==high_score]
            if len(leaders)==1:
                self.log(f"우승: {leaders[0].name}", "contest/performance-stage")
            else:
                self.log("최고점 동률: "+", ".join(c.name for c in leaders)+" (단독 우승 판정 미확정)", "contest/performance-stage")
            HALLS.award_contest(self)
            return final
        finally:
            self._standard_busy=False


def demo_contestants():
    """챕터 8 데모: 주뱃·내루미·입치트, 귀여움 콘테스트."""
    return [
        Contestant("내루미", {"귀여움": 2}, ["헤롱헤롱", "아쿠아테일", "웅크리기"], "매력", 5, "귀여움"),
        Contestant("주뱃", {"슬기로움": 3}, ["유턴", "이상한빛", "화풀이"], "매력", 4, "귀여움"),
        Contestant("입치트", {"아름다움": 2}, ["달콤한향기", "거짓울음", "기가임팩트"], "교활", 4, "귀여움", trainer_edges=["edge/우아함"]),
    ]


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="PTK contest demo with explicit ruleset selection")
    parser.add_argument("root", nargs="?", default=".")
    parser.add_argument("seed", nargs="?", type=int, default=3)
    parser.add_argument("--ruleset", default=None)
    args = parser.parse_args()
    root, seed = args.root, args.seed
    rules = ContestRules(root, ruleset=args.ruleset)
    eng = ContestEngine(rules, seed)
    cs = demo_contestants()

    def chooser(c, rnd, adjacent, center):
        mv = c.moves[(rnd - 1) % len(c.moves)]
        stat, _ = rules.move_contest(mv)
        return mv, 3 if c.stat_dice.get(stat, 0) >= 3 else c.stat_dice.get(stat, 0)
    eng.run(cs, "귀여움", chooser)
    out = "\n".join(eng.log_lines) + "\n"
    open(os.path.join(root, "output/pilot-contest-log.md"), "w", encoding="utf-8").write(out)
    print(out)
