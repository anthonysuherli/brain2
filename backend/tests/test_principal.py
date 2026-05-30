from brain2.agent.state import Principal

def test_principal_defaults_to_user():
    p = Principal(user_id="u1", org_id="o1", access_token="tok")
    assert p.is_service is False
    assert (p.user_id, p.org_id, p.access_token) == ("u1", "o1", "tok")
