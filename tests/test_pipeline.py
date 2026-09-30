"""Pipeline behavior with a scripted model. No network."""

import json

import pytest

from app.models.internal import AdaptError
from app.services.pipeline import adapt
from tests.helpers import FakeLLM, entry, mapping, qid

COMPANY = {
    "type": "object",
    "properties": {
        "company_name": {"type": "string"},
        "employee_count": {"type": ["integer", "null"]},
        "funding_usd": {"type": ["number", "null"]},
        "city": {"type": ["string", "null"]},
    },
    "required": ["company_name"],
}


def run(content_type, data, schema, *responses, instructions=None):
    llm = FakeLLM(*responses)
    return adapt(content_type, data, schema, instructions, llm), llm


# ---------------------------------------------------------------- input types


def test_clean_json():
    src = {"company_name": "Acme", "employee_count": 240, "funding_usd": 12000000, "city": "Austin"}
    result, llm = run(
        "json",
        src,
        COMPANY,
        mapping(
            entry("company_name", "Acme", evidence="Acme"),
            entry("employee_count", 240, formula=qid("json", src, "240")),
            entry("funding_usd", 12000000, formula=qid("json", src, "12000000")),
            entry("city", "Austin", evidence="Austin"),
        ),
    )
    assert result.valid
    assert result.data == src
    assert result.warnings == []
    assert len(llm.calls) == 1


def test_messy_json_normalizes_values_in_code():
    src = {"name": "Acme", "staff": "~240", "funding": "$12M", "hq": "SF"}
    result, _ = run(
        "json",
        src,
        COMPANY,
        mapping(
            entry("company_name", "Acme", evidence="Acme"),
            entry("employee_count", 240, evidence="~240", formula=qid("json", src, "240")),
            entry("funding_usd", 12, evidence="$12M", formula=qid("json", src, "$12M")),
            entry("city", "San Francisco", evidence="SF", interpretation="SF is the common abbreviation"),
        ),
    )
    assert result.valid
    assert result.data == {"company_name": "Acme", "employee_count": 240, "funding_usd": 12_000_000, "city": "San Francisco"}
    assert any("employee_count" in w and "approximate" in w for w in result.warnings)
    assert any("city: interpreted source text 'SF'" in w for w in result.warnings)
    assert any("funding_usd" in w and "did not match" in w for w in result.warnings)


def test_raw_text_with_spelled_out_number():
    text = "Acme is a team of roughly two hundred people based in Austin."
    result, _ = run(
        "text",
        text,
        COMPANY,
        mapping(
            entry("company_name", "Acme", evidence="Acme"),
            entry("employee_count", 200, evidence="roughly two hundred people", formula=qid("text", text, "two hundred")),
            entry("funding_usd", None, missing=True),
            entry("city", "Austin", evidence="Austin"),
        ),
    )
    assert result.valid
    assert result.data == {"company_name": "Acme", "employee_count": 200, "funding_usd": None, "city": "Austin"}
    assert "funding_usd: not present in source; set to null" in result.warnings
    assert any("employee_count" in w and "approximate" in w for w in result.warnings)


def test_csv_source():
    csv_text = "company,headcount,raised\nAcme,240,$12M"
    result, _ = run(
        "csv",
        csv_text,
        COMPANY,
        mapping(
            entry("company_name", "Acme", evidence="Acme"),
            entry("employee_count", 240, formula=qid("csv", csv_text, "240")),
            entry("funding_usd", 12000000, formula=qid("csv", csv_text, "$12M")),
            entry("city", None, missing=True),
        ),
    )
    assert result.valid
    assert result.data["funding_usd"] == 12_000_000
    assert result.data["city"] is None


# ---------------------------------------------------------------- missing values and honesty


def test_missing_optional_field_is_null_with_warning():
    result, _ = run(
        "json",
        {"name": "Acme"},
        COMPANY,
        mapping(
            entry("company_name", "Acme", evidence="Acme"),
            entry("employee_count", None, missing=True),
            entry("funding_usd", None, missing=True),
            entry("city", None, missing=True),
        ),
    )
    assert result.valid
    assert result.data == {"company_name": "Acme", "employee_count": None, "funding_usd": None, "city": None}
    assert "city: not present in source; set to null" in result.warnings


def test_oversized_source_warns_that_it_was_truncated():
    text = "Acme. " + "filler " * 4000
    result, _ = run(
        "text",
        text,
        COMPANY,
        mapping(
            entry("company_name", "Acme", evidence="Acme"),
            entry("employee_count", None, missing=True),
            entry("funding_usd", None, missing=True),
            entry("city", None, missing=True),
        ),
    )
    assert result.warnings[0].startswith("source: only the first 20000 of")


def test_missing_required_field_is_invalid_without_a_repair_call():
    result, llm = run(
        "json",
        {"staff": "240"},
        COMPANY,
        mapping(
            entry("company_name", None, missing=True),
            entry("employee_count", 240, formula="q1"),
            entry("funding_usd", None, missing=True),
            entry("city", None, missing=True),
        ),
    )
    assert not result.valid
    assert "company_name" not in result.data
    assert "company_name: required by target_schema but not found in source" in result.warnings
    assert len(llm.calls) == 1, "repairing would only pressure the model to invent the value"


def test_fabricated_values_are_dropped():
    src = {"name": "Acme"}
    result, _ = run(
        "json",
        src,
        COMPANY,
        mapping(
            entry("company_name", "Acme", evidence="Acme"),
            entry("employee_count", 50, interpretation="typical startup size"),
            entry("funding_usd", 5000000, evidence="Acme"),
            entry("city", "Paris", evidence="headquarters"),
        ),
    )
    assert result.valid
    assert result.data == {"company_name": "Acme", "employee_count": None, "funding_usd": None, "city": None}
    assert sum("dropped model value" in w for w in result.warnings) == 3


@pytest.mark.parametrize("formula", ["1", "2 * 0.5", "q1 / q1", "q1 - q1 + 1"])
def test_formulas_that_ignore_the_source_are_rejected(gpu_schema, formula):
    src = "E,H100,80 GB,$3.10 per GPU / hour,US West"
    result, _ = run(
        "csv",
        src,
        gpu_schema,
        mapping(
            entry("provider", "E", evidence="E"),
            entry("gpu", "H100", evidence="H100"),
            entry("gpu_count", 1, evidence="per GPU", formula=formula),
            entry("vram_gb", None, missing=True),
            entry("price_per_gpu_hour_usd", None, missing=True),
            entry("region", None, missing=True),
            entry("price_type", None, missing=True),
        ),
    )
    assert result.data["gpu_count"] is None
    assert any("does not depend on any source value" in w for w in result.warnings)


def test_enum_label_must_be_stated_in_source(gpu_schema):
    src = "E,H100,80 GB,$3.10 per GPU / hour,US West"
    result, _ = run(
        "csv",
        src,
        gpu_schema,
        mapping(
            entry("provider", "E", evidence="E"),
            entry("gpu", "H100", evidence="H100"),
            entry("gpu_count", None, missing=True),
            entry("vram_gb", None, missing=True),
            entry("price_per_gpu_hour_usd", None, missing=True),
            entry("region", None, missing=True),
            entry("price_type", "on_demand", evidence="$3.10 per GPU / hour", interpretation="plain listed price"),
        ),
    )
    assert result.data["price_type"] is None
    assert any("label is not stated in the source" in w for w in result.warnings)


def test_null_sentinels_become_null():
    src = {"name": "Acme", "hq": "N/A"}
    result, _ = run(
        "json",
        src,
        COMPANY,
        mapping(
            entry("company_name", "Acme", evidence="Acme"),
            entry("employee_count", None, missing=True),
            entry("funding_usd", None, missing=True),
            entry("city", "N/A", evidence="N/A"),
        ),
    )
    assert result.data["city"] is None


# ---------------------------------------------------------------- repair


def test_malformed_model_output_takes_the_repair_path():
    good = mapping(
        entry("company_name", "Acme", evidence="Acme"),
        entry("employee_count", None, missing=True),
        entry("funding_usd", None, missing=True),
        entry("city", None, missing=True),
    )
    result, llm = run("json", {"name": "Acme"}, COMPANY, "Sure! Here is the mapping: {oops", good)
    assert result.valid
    assert result.repaired
    assert len(llm.calls) == 2
    assert "not valid JSON" in llm.calls[1][-1]["content"]


def test_fenced_json_is_accepted_without_repair():
    body = mapping(
        entry("company_name", "Acme", evidence="Acme"),
        entry("employee_count", None, missing=True),
        entry("funding_usd", None, missing=True),
        entry("city", None, missing=True),
    )
    result, llm = run("json", {"name": "Acme"}, COMPANY, f"```json\n{body}\n```")
    assert result.valid and len(llm.calls) == 1


def test_still_malformed_after_repair_is_invalid():
    result, llm = run("json", {"name": "Acme"}, COMPANY, "not json", json.dumps({"fields": "wrong"}))
    assert not result.valid
    assert result.repaired
    assert any("mapping failed after one repair attempt" in w for w in result.warnings)
    assert len(llm.calls) == 2


def test_invalid_after_repair_is_invalid():
    fabricated = mapping(
        entry("company_name", "Globex", evidence="company"),
        entry("employee_count", None, missing=True),
        entry("funding_usd", None, missing=True),
        entry("city", None, missing=True),
    )
    result, llm = run("json", {"staff": 12}, COMPANY, fabricated, fabricated)
    assert not result.valid
    assert result.repaired
    assert len(llm.calls) == 2
    assert "company_name" in llm.calls[1][-1]["content"]


def test_repair_can_fix_a_bad_formula():
    src = {"price": "$19.92/hr", "instance": "8xH100"}
    schema = {"type": "object", "properties": {"unit_price": {"type": "number"}}, "required": ["unit_price"]}
    bad = mapping(entry("unit_price", 2.49, formula="q7 / q1"))
    good = mapping(entry("unit_price", 2.49, formula=f"{qid('json', src, '$19.92')} / {qid('json', src, '8x')}"))
    result, llm = run("json", src, schema, bad, good)
    assert result.valid and result.repaired
    assert result.data == {"unit_price": 2.49}


# ---------------------------------------------------------------- arithmetic semantics


def test_model_arithmetic_is_recomputed(gpu_schema):
    src = {"instance": "8xH100 SXM", "price": "$19.92/hr"}
    result, _ = run(
        "json",
        src,
        gpu_schema,
        mapping(
            entry("provider", "B", evidence="B"),
            entry("gpu", "H100 SXM", evidence="8xH100 SXM"),
            entry("gpu_count", 8, formula=qid("json", src, "8x")),
            entry("vram_gb", None, missing=True),
            entry("price_per_gpu_hour_usd", 2.5, formula=f"{qid('json', src, '$19.92')} / {qid('json', src, '8x')}"),
            entry("region", None, missing=True),
            entry("price_type", None, missing=True),
        ),
        instructions="The provider name is B.",
    )
    assert result.data["price_per_gpu_hour_usd"] == 2.49
    assert any("did not match its own formula" in w for w in result.warnings)


def test_enum_labels_are_snapped(gpu_schema):
    src = {"gpu": "H100", "billing": "On-Demand"}
    result, _ = run(
        "json",
        src,
        gpu_schema,
        mapping(
            entry("provider", "A", evidence="A"),
            entry("gpu", "H100", evidence="H100"),
            entry("gpu_count", None, missing=True),
            entry("vram_gb", None, missing=True),
            entry("price_per_gpu_hour_usd", None, missing=True),
            entry("region", None, missing=True),
            entry("price_type", "On-Demand", evidence="On-Demand"),
        ),
        instructions="provider is A",
    )
    assert result.valid
    assert result.data["price_type"] == "on_demand"


def test_integer_field_gets_integer():
    src = {"gpus": "8"}
    schema = {"type": "object", "properties": {"n": {"type": "integer"}}, "required": ["n"]}
    result, _ = run("json", src, schema, mapping(entry("n", "8", formula="q1")))
    assert result.data == {"n": 8} and isinstance(result.data["n"], int)


# ---------------------------------------------------------------- shapes


def test_array_target_maps_each_element():
    src = [{"name": "Acme"}, {"name": "Globex"}]
    schema = {
        "type": "array",
        "items": {"type": "object", "properties": {"company_name": {"type": "string"}}, "required": ["company_name"]},
    }
    result, llm = run(
        "json",
        src,
        schema,
        mapping(entry("company_name", "Acme", evidence="Acme")),
        mapping(entry("company_name", "Globex", evidence="Globex")),
    )
    assert result.valid
    assert result.data == [{"company_name": "Acme"}, {"company_name": "Globex"}]
    assert len(llm.calls) == 2


def test_list_source_into_object_target_warns():
    src = [{"name": "Acme"}, {"name": "Globex"}]
    result, _ = run(
        "json",
        src,
        COMPANY,
        mapping(
            entry("company_name", "Acme", evidence="Acme"),
            entry("employee_count", None, missing=True),
            entry("funding_usd", None, missing=True),
            entry("city", None, missing=True),
        ),
    )
    assert "source is a list of 2 items" in result.warnings[0]


def test_unknown_model_fields_are_ignored():
    result, _ = run(
        "json",
        {"name": "Acme"},
        COMPANY,
        mapping(
            entry("company_name", "Acme", evidence="Acme"),
            entry("ceo", "Wile E.", evidence=""),
            entry("employee_count", None, missing=True),
            entry("funding_usd", None, missing=True),
            entry("city", None, missing=True),
        ),
    )
    assert "ceo" not in result.data
    assert any("unknown field 'ceo'" in w for w in result.warnings)


@pytest.mark.parametrize(
    "schema",
    [
        {"type": "string"},
        {"type": "object"},
        {"type": "array", "items": {"type": "string"}},
    ],
)
def test_unsupported_target_shapes_fail_cleanly(schema):
    with pytest.raises(AdaptError):
        adapt("json", {"a": 1}, schema, None, FakeLLM())


def test_prompt_contains_schema_source_and_quantities(gpu_schema):
    llm = FakeLLM(mapping(entry("provider", None, missing=True)), mapping(entry("provider", None, missing=True)))
    adapt("text", "H100 SXM, 8x80 GB, starting at $24.80/hr", gpu_schema, "provider is C", llm)
    prompt = llm.calls[0][1]["content"]
    assert "price_per_gpu_hour_usd" in prompt
    assert "starting at $24.80/hr" in prompt
    assert "qualifiers=floor" in prompt
    assert "provider is C" in prompt
