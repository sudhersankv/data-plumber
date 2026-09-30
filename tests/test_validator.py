import pytest

from app.models.internal import AdaptError
from app.services.validator import check_target_schema, missing_required, validation_errors


def test_valid_instance(gpu_schema):
    assert validation_errors({"provider": "A", "gpu": "H100"}, gpu_schema) == []


def test_type_error_is_reported_with_path(gpu_schema):
    errors = validation_errors({"provider": "A", "gpu": "H100", "gpu_count": "eight"}, gpu_schema)
    assert errors and errors[0].startswith("gpu_count:")


def test_enum_enforced(gpu_schema):
    assert validation_errors({"provider": "A", "gpu": "H100", "price_type": "cheap"}, gpu_schema)


def test_missing_required(gpu_schema):
    assert missing_required({"provider": "A"}, gpu_schema) == ["gpu"]


@pytest.mark.parametrize("schema", [{}, [], {"type": "nonsense"}, {"properties": {"a": {"type": 5}}}])
def test_invalid_target_schema_rejected(schema):
    with pytest.raises(AdaptError):
        check_target_schema(schema)
