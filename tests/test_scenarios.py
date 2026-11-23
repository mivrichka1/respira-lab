import inspect

from respira.scales import SSE_SCALES
from respira.scenarios import PROFILES, build_scenario, next_scenario

SCALES = {scale.__name__: scale for scale in SSE_SCALES}


def test_random_case_does_not_repeat_current_family():
    for key in PROFILES:
        assert all(next_scenario(key)["id"] != key for _ in range(20))


def test_generated_cases_cover_distinct_valid_workflows():
    targets = set()
    prompts = set()
    for key in PROFILES:
        example = build_scenario(key)
        targets.add(example["targets"])
        prompts.add(example["prompt"])
        for _ in range(10):
            item = build_scenario(key, vary=True)
            for _, tool in item["targets"]:
                scale = SCALES[tool]
                arguments = {name: item["values"][name] for name in inspect.signature(scale).parameters}
                assert isinstance(scale(**arguments)["value"], (int, float))
    assert len(targets) == len(prompts) == len(PROFILES)
    assert all(build_scenario(key)["research"] for key in PROFILES)
    assert build_scenario("hypercapnia")["values"]["spo2_scale"] == "2"
