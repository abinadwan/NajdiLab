from pathlib import Path
import re
import pytest
from app import service, training_control


def test_invalid_message_role_is_reported_in_english(tmp_path):
    with pytest.raises(service.ValidationError, match='Invalid role'):
        service.add_message({'role': 'invalid'}, tmp_path / 'unused.db')
    assert not (tmp_path / 'unused.db').exists()


def test_required_field_is_reported_in_english(tmp_path):
    with pytest.raises(service.ValidationError, match='Required field: role'):
        service.add_message({}, tmp_path / 'unused.db')


def test_model_identifier_error_keeps_machine_code_and_english_message(tmp_path, monkeypatch):
    with pytest.raises(training_control.TrainingControlError) as exc:
        training_control.get_model('../escape')
    assert exc.value.code == 'MODEL_NOT_FOUND'
    assert not re.search(r'[\u0600-\u06ff]', str(exc.value))
