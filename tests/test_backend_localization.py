import pytest
from app import service


def test_invalid_message_role_is_reported_in_english(tmp_path):
    with pytest.raises(service.ValidationError, match='Invalid role'):
        service.add_message({'role': 'invalid'}, tmp_path / 'unused.db')
    assert not (tmp_path / 'unused.db').exists()


def test_required_field_is_reported_in_english(tmp_path):
    with pytest.raises(service.ValidationError, match='Required field: role'):
        service.add_message({}, tmp_path / 'unused.db')
