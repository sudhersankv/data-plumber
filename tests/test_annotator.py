from app.services.annotator import annotate
from app.services.parser import parse_source


def quantities(content_type, data, instructions=None):
    return annotate(parse_source(content_type, data), instructions)


def test_money_suffix_millions():
    (q,) = quantities("json", {"funding": "$12M"})
    assert (q.kind, q.value, q.unit) == ("money", 12_000_000, "USD")


def test_hourly_rate():
    (q,) = quantities("text", "costs $24.80/hr")
    assert (q.value, q.per, q.per_item) == (24.8, "hour", None)


def test_per_gpu_per_hour_rate():
    (q,) = quantities("text", "$3.10 per GPU / hour")
    assert (q.value, q.per, q.per_item) == (3.1, "hour", "gpu")


def test_count_times_size():
    qs = quantities("text", "8x80 GB")
    assert [(q.kind, q.value) for q in qs] == [("count", 8), ("size", 80)]


def test_count_prefix_on_word():
    (q,) = quantities("json", {"instance": "8xH100"})
    assert (q.kind, q.value) == ("count", 8)


def test_size_embedded_in_sku():
    (q,) = quantities("json", {"sku": "h100-80gb"})
    assert (q.kind, q.value, q.unit) == ("size", 80, "GB")


def test_starting_at_is_a_floor():
    qs = quantities("text", "H100 SXM, 8x80 GB, starting at $24.80/hr, US-West")
    money = next(q for q in qs if q.kind == "money")
    assert money.qualifiers == ["floor"]
    assert all(not q.qualifiers for q in qs if q.kind != "money")


def test_approximate_number():
    (q,) = quantities("json", {"staff": "~240"})
    assert (q.value, q.qualifiers) == (240, ["approximate"])


def test_null_sentinel():
    (q,) = quantities("json", {"ipo": "N/A"})
    assert (q.kind, q.value) == ("null", None)


def test_json_numbers_keep_their_path():
    qs = quantities("json", {"rate": 0.00082, "nested": {"gpus": 8}})
    assert [(q.path, q.value) for q in qs] == [("rate", 0.00082), ("nested.gpus", 8)]


def test_ids_are_sequential_and_instructions_are_scanned():
    qs = quantities("text", "$5/hr", instructions="the machine has 4 GPUs")
    assert [q.id for q in qs] == ["q1", "q2"]
    assert qs[1].path == "instructions" and qs[1].value == 4


def test_spelled_out_numbers():
    qs = quantities("text", "a team of roughly two hundred people and twenty-five thousand users")
    assert [(q.raw, q.value, q.qualifiers) for q in qs] == [
        ("two hundred", 200, ["approximate"]),
        ("twenty-five thousand", 25_000, []),
    ]


def test_region_digits_do_not_break_money():
    qs = quantities("json", {"loc": "us-west-1", "price": "$2.49"})
    assert any(q.kind == "money" and q.value == 2.49 for q in qs)
