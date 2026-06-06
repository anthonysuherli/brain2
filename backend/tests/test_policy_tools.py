from br8n.interfaces.mcp import server


def test_policy_get_default_then_set(tmp_path):
    g = server._policy_get_impl("proj", "main", str(tmp_path))
    assert [s["name"] for s in g["policy"]["sections"]] == [
        "Decisions", "Changes", "Open Questions", "Next Steps"]
    assert g["policy"]["steer"] == ""
    out = server._policy_set_impl("proj", "main", str(tmp_path),
                            {"sections": [{"name": "Decisions", "enabled": True}],
                             "steer": "be terse"})
    assert out.get("ok") is True
    g2 = server._policy_get_impl("proj", "main", str(tmp_path))
    assert g2["policy"]["steer"] == "be terse"
    assert len(g2["policy"]["sections"]) == 1


def test_policy_set_validation_error(tmp_path):
    # a section missing the required 'name' field → validation error, not a crash
    out = server._policy_set_impl("proj", "main", str(tmp_path),
                                  {"sections": [{"enabled": True}], "steer": "x"})
    assert "errors" in out
    assert out.get("ok") is not True
