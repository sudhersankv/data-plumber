"""All five demo providers normalize into one schema, and the planner's math is right.

The model is scripted here with the mapping a correct model returns (checked live in
test_live_fireworks.py). The numbers are recomputed by code from the annotated quantities.
"""

import pytest

from app.services.pipeline import adapt
from demo.providers import PROVIDERS, adapt_request, load_payload
from demo.run_demo import choose, plan
from tests.helpers import FakeLLM, entry, mapping, qid

BY_ID = {p.id: p for p in PROVIDERS}


def scripted_mapping(pid: str, ct: str, data, instructions) -> str:
    q = lambda raw, kind=None: qid(ct, data, raw, kind, instructions)  # noqa: E731
    if pid == "A":
        return mapping(
            entry("provider", "A", evidence="The provider name is A."),
            entry("gpu", "H100 SXM", evidence="H100 SXM"),
            entry("gpu_count", 8, formula=q("8", "number")),
            entry("vram_gb", 80, formula=q("80GB")),
            entry("price_per_gpu_hour_usd", 2.49, formula=q("2.49")),
            entry("region", "us-west-1", evidence="us-west-1"),
            entry("price_type", "on_demand", evidence="on-demand"),
        )
    if pid == "B":
        return mapping(
            entry("provider", "B", evidence="The provider name is B."),
            entry("gpu", "H100 SXM", evidence="8xH100 SXM"),
            entry("gpu_count", 8, formula=q("8x", "count")),
            entry("vram_gb", None, missing=True),
            entry(
                "price_per_gpu_hour_usd",
                2.49,
                evidence="$19.92/hr",
                interpretation="whole-machine hourly price",
                formula=f"{q('$19.92')} / {q('8x', 'count')}",
            ),
            entry("region", "Oregon", evidence="Oregon"),
            entry("price_type", "on_demand", evidence="on-demand"),
            warnings=["$19.92/hr is for the whole 8-GPU instance; divided by 8."],
        )
    if pid == "C":
        return mapping(
            entry("provider", "C", evidence="The provider name is C."),
            entry("gpu", "H100 SXM", evidence="H100 SXM"),
            entry("gpu_count", 8, formula=q("8x80", "count")),
            entry("vram_gb", 80, formula=q("8x80", "size")),
            entry(
                "price_per_gpu_hour_usd",
                3.1,
                evidence="starting at $24.80/hr",
                interpretation="floor price for the 8-GPU machine",
                formula=f"{q('$24.80')} / {q('8x80', 'count')}",
            ),
            entry("region", "US-West", evidence="US-West"),
            entry("price_type", "starting_at", evidence="starting at"),
        )
    if pid == "D":
        return mapping(
            entry("provider", "D", evidence="The provider name is D."),
            entry("gpu", "NVIDIA H100 80GB", evidence="NVIDIA H100 80GB"),
            entry("gpu_count", 8, formula=q("8", "number")),
            entry("vram_gb", 80, formula=q("80GB")),
            entry(
                "price_per_gpu_hour_usd",
                2.95,
                evidence="USD/GPU-second",
                interpretation="per-GPU per-second rate",
                formula=f"{q('0.00082')} * SECONDS_PER_HOUR",
            ),
            entry("region", "us-west2", evidence="us-west2"),
            entry("price_type", "on_demand", evidence="on-demand"),
        )
    if pid == "E":
        return mapping(
            entry("provider", "E", evidence="E"),
            entry("gpu", "H100", evidence="H100"),
            entry("gpu_count", None, missing=True),
            entry("vram_gb", 80, formula=q("80 GB")),
            entry("price_per_gpu_hour_usd", 3.1, formula=q("$3.10")),
            entry("region", "US West", evidence="US West"),
            entry("price_type", None, missing=True),
        )
    raise AssertionError(pid)


def run_provider(pid: str, content_type: str | None = None):
    provider = BY_ID[pid]
    ct = content_type or provider.content_type
    data = load_payload(provider)
    body = adapt_request(provider, ct, data)
    llm = FakeLLM(scripted_mapping(pid, ct, data, provider.instructions))
    return adapt(ct, data, body["target_schema"], provider.instructions, llm)


EXPECTED = {
    "A": {
        "provider": "A",
        "gpu": "H100 SXM",
        "gpu_count": 8,
        "vram_gb": 80,
        "price_per_gpu_hour_usd": 2.49,
        "region": "us-west-1",
        "price_type": "on_demand",
    },
    "B": {
        "provider": "B",
        "gpu": "H100 SXM",
        "gpu_count": 8,
        "vram_gb": None,
        "price_per_gpu_hour_usd": 2.49,
        "region": "Oregon",
        "price_type": "on_demand",
    },
    "C": {
        "provider": "C",
        "gpu": "H100 SXM",
        "gpu_count": 8,
        "vram_gb": 80,
        "price_per_gpu_hour_usd": 3.1,
        "region": "US-West",
        "price_type": "starting_at",
    },
    "D": {
        "provider": "D",
        "gpu": "NVIDIA H100 80GB",
        "gpu_count": 8,
        "vram_gb": 80,
        "price_per_gpu_hour_usd": 2.952,
        "region": "us-west2",
        "price_type": "on_demand",
    },
    "E": {
        "provider": "E",
        "gpu": "H100",
        "gpu_count": None,
        "vram_gb": 80,
        "price_per_gpu_hour_usd": 3.1,
        "region": "US West",
        "price_type": None,
    },
}


@pytest.mark.parametrize("pid", list(EXPECTED))
def test_provider_normalizes(pid):
    result = run_provider(pid)
    assert result.valid, result.warnings
    assert result.data == EXPECTED[pid]


def test_whole_machine_price_becomes_per_gpu_hour():
    result = run_provider("B")
    price = next(t for t in result.trace if t["field"] == "price_per_gpu_hour_usd")
    assert price["derived"] is True
    assert price["formula"] == "19.92 / 8"
    assert price["source_value"] == "$19.92/hr"


def test_per_second_price_becomes_per_hour_and_model_rounding_is_corrected():
    result = run_provider("D")
    assert result.data["price_per_gpu_hour_usd"] == 2.952
    assert any("did not match its own formula" in w for w in result.warnings)


def test_starting_at_is_preserved_for_the_fallback_scrape():
    result = run_provider("C")
    assert result.data["price_type"] == "starting_at"
    assert "price_per_gpu_hour_usd: source value is a lower bound ('$24.80/hr'), not a firm value" in result.warnings


def test_missing_vram_is_not_fabricated():
    result = run_provider("B")
    assert result.data["vram_gb"] is None
    assert "vram_gb: not present in source; set to null" in result.warnings


def test_trace_is_available_in_debug_form():
    result = run_provider("C")
    assert result.to_response(debug=True)["trace"]
    assert "trace" not in result.to_response(debug=False)


def rows():
    return [{"provider_id": pid, **run_provider(pid).to_response()} for pid in EXPECTED]


def test_planner_costs_and_choice():
    planned = {p["provider"]: p for p in plan(rows())}
    assert planned["A"]["job_cost_usd"] == 119.52
    assert planned["B"]["job_cost_usd"] == 119.52
    assert planned["D"]["job_cost_usd"] == 141.70
    assert planned["E"]["job_cost_usd"] == 148.80
    assert planned["C"]["job_cost_usd"] == 148.80
    assert planned["C"]["eligible"] is False and "floor" in planned["C"]["status"]
    assert all(planned[p]["eligible"] for p in "ABDE")

    pick = choose(list(planned.values()))
    assert pick["provider"] == "A", "A and B tie on cost; A has fewer warnings"


def test_planner_excludes_invalid_and_priceless_rows():
    planned = plan(
        [
            {"provider_id": "X", "valid": False, "data": {"provider": "X"}, "warnings": []},
            {
                "provider_id": "Y",
                "valid": True,
                "data": {"provider": "Y", "region": "US West", "price_per_gpu_hour_usd": None},
                "warnings": [],
            },
            {
                "provider_id": "Z",
                "valid": True,
                "data": {"provider": "Z", "region": "eu-central", "price_per_gpu_hour_usd": 1.0},
                "warnings": [],
            },
        ]
    )
    assert [p["status"] for p in planned] == ["excluded: invalid row", "excluded: no price", "excluded: not US West"]
    assert choose(planned) is None
