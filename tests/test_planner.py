from app.planner import extract_phone, fallback_plan
from app.models import valid_phone
from app.security import validate_twilio_request
from app.config import get_settings


def test_phone_extraction_and_validation():
    assert valid_phone('+919876543210')
    assert not valid_phone('9876543210')
    assert not valid_phone('+0000000')
    assert extract_phone('Call +14155552671 now','')=='+14155552671'
    assert extract_phone('Call +14155552671 now','+919876543210')=='+919876543210'


def test_template_does_not_invent_booking():
    plan=fallback_plan('Ask about booking')
    assert 'invent' in ' '.join(plan['agenda'])
    assert len(plan['agenda'])>=3
