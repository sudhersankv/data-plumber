import pytest

from app.models.internal import AdaptError
from app.services.parser import parse_source


def test_json_object_passes_through():
    parsed = parse_source("json", {"a": 1})
    assert parsed.value == {"a": 1}
    assert parsed.text == '{"a": 1}'


def test_json_string_is_decoded():
    assert parse_source("json", '{"a": [1, 2]}').value == {"a": [1, 2]}


def test_json_array():
    assert parse_source("json", [{"a": 1}, {"a": 2}]).value == [{"a": 1}, {"a": 2}]


def test_malformed_json_fails_cleanly():
    with pytest.raises(AdaptError, match="not valid JSON"):
        parse_source("json", '{"a": ')


@pytest.mark.parametrize("data", [42, '"just a string"', {}, []])
def test_json_must_be_non_empty_object_or_array(data):
    with pytest.raises(AdaptError):
        parse_source("json", data)


def test_csv_with_header_single_row_becomes_object():
    parsed = parse_source("csv", "provider,price\nE,$3.10\n")
    assert parsed.value == {"provider": "E", "price": "$3.10"}


def test_csv_with_header_many_rows_becomes_list():
    parsed = parse_source("csv", "name,count\nx,1\ny,2")
    assert parsed.value == [{"name": "x", "count": "1"}, {"name": "y", "count": "2"}]


def test_headerless_csv_uses_positional_columns():
    parsed = parse_source("csv", "E,H100,80 GB,$3.10 per GPU / hour,US West")
    assert parsed.value == {"col_1": "E", "col_2": "H100", "col_3": "80 GB", "col_4": "$3.10 per GPU / hour", "col_5": "US West"}


def test_text_is_stripped():
    assert parse_source("text", "  hello \n").value == "hello"


@pytest.mark.parametrize("content_type", ["text", "csv"])
def test_text_and_csv_require_string(content_type):
    with pytest.raises(AdaptError, match="must be a string"):
        parse_source(content_type, {"a": 1})


def test_empty_text_rejected():
    with pytest.raises(AdaptError, match="empty"):
        parse_source("text", "   ")


def test_unknown_content_type_rejected():
    with pytest.raises(AdaptError):
        parse_source("html", "<p>x</p>")
