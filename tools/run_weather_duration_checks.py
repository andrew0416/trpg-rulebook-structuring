"""Run the staged weather-rock checks plus the directly affected weather suite."""
import importlib.util
import io
from pathlib import Path
import sys
import unittest

STAGE = Path(__file__).resolve().parents[1]
ROOT = Path(r"D:\trpg-rulebook-structuring\ptk-structure-experiment")
sys.path[:0] = [str(STAGE / "engine"), str(STAGE / "tools"), str(ROOT / "engine"), str(ROOT / "tools")]


def stage_module(name):
    spec = importlib.util.spec_from_file_location(name, STAGE / "engine" / (name + ".py"))
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)


for module_name in ("weather_duration_items", "homebrew_weather", "weather_state"):
    stage_module(module_name)


def run(label, test_names, filename):
    suite = unittest.TestSuite()
    loader = unittest.defaultTestLoader
    for test_name in test_names:
        suite.addTests(loader.loadTestsFromName(test_name))
    stream = io.StringIO()
    result = unittest.TextTestRunner(stream=stream, verbosity=2).run(suite)
    text = stream.getvalue()
    header = (
        f"{label}: tests={result.testsRun} failures={len(result.failures)} "
        f"errors={len(result.errors)} skipped={len(result.skipped)}\n\n"
    )
    output = header + text
    (STAGE / "data" / "verification" / filename).write_text(output, encoding="utf-8")
    sys.stdout.write(output)
    return result.wasSuccessful()


direct = run(
    "weather-duration-items-direct",
    ["test_category2_weather_duration_items.Tests"],
    "weather-duration-items-direct-checks.log",
)
related = run(
    "weather-duration-items-related",
    [
        "test_category2_weather_state.Tests",
        "test_category2_homebrew_weather.Tests.test_actual_source_admission_and_exclusion_do_not_depend_on_profile_name",
        "test_category2_homebrew_weather.Tests.test_core_and_core_errata_keep_finite_weather_and_ambient_effects",
        "test_category2_homebrew_weather.Tests.test_existing_explicit_gm_effect_override_is_applied_after_policy_overlay",
        "test_category2_homebrew_weather.Tests.test_four_native_moves_and_both_actor_kinds_keep_metadata_and_real_costs",
        "test_category2_homebrew_weather.Tests.test_replacement_gm_clear_and_independent_finite_weather_have_distinct_lifetimes",
        "test_category2_homebrew_weather.Tests.test_snapshot_codec_wrong_profile_and_tampering_reject_atomically",
    ],
    "weather-duration-items-related-checks.log",
)
raise SystemExit(0 if direct and related else 1)
