"""Unit tests for br8n.knowledge_graph.schema — pure validation logic."""

from __future__ import annotations

from br8n.knowledge_graph.schema import KGSchema, validate_schema


def test_validate_schema_flags_dangling_relation_validity():
    schema = KGSchema.model_validate({
        "node_types": [{"name": "service", "description": "a service", "examples": [],
                        "attributes": [], "layer": ""}],
        "relation_types": [{"name": "calls", "description": "x calls y"}],
        "relation_validity": [{"source_type": "service", "target_type": "ghost"}],
        "competency_questions": ["what calls what?"],
        "regime": "soft",
    })
    errors = validate_schema(schema)
    assert any("ghost" in e for e in errors)


def test_validate_schema_accepts_clean_schema():
    schema = KGSchema.model_validate({
        "node_types": [{"name": "service", "description": "a service", "examples": [],
                        "attributes": [{"name": "lang", "type": "text", "required": False,
                                        "description": "language"}], "layer": ""}],
        "relation_types": [{"name": "calls", "description": "x calls y"}],
        "relation_validity": [{"source_type": "service", "target_type": "service"}],
        "competency_questions": ["what calls what?"],
        "regime": "soft",
    })
    assert validate_schema(schema) == []


def test_validate_schema_flags_bad_attribute_type():
    schema = KGSchema.model_validate({
        "node_types": [{"name": "service", "description": "a service", "examples": [],
                        "attributes": [{"name": "version", "type": "integer", "required": False,
                                        "description": "version number"}], "layer": ""}],
        "relation_types": [],
        "relation_validity": [],
        "competency_questions": [],
        "regime": "soft",
    })
    errors = validate_schema(schema)
    assert any("integer" in e for e in errors)


def test_validate_schema_flags_empty_node_types():
    schema = KGSchema.model_validate({
        "node_types": [],
        "relation_types": [],
        "relation_validity": [],
        "competency_questions": [],
        "regime": "soft",
    })
    errors = validate_schema(schema)
    assert any("no node_types" in e for e in errors)


def test_validate_schema_flags_empty_string_relation_validity():
    schema = KGSchema.model_validate({
        "node_types": [{"name": "service", "description": "s", "examples": [], "attributes": [], "layer": ""}],
        "relation_types": [{"name": "calls", "description": "x calls y"}],
        "relation_validity": [{"source_type": "", "target_type": "service"}],
        "competency_questions": [],
        "regime": "soft",
    })
    errors = validate_schema(schema)
    assert len(errors) > 0


def test_validate_schema_flags_duplicate_attribute_name():
    schema = KGSchema.model_validate({
        "node_types": [{"name": "service", "description": "a service", "examples": [],
                        "attributes": [
                            {"name": "lang", "type": "text", "required": False, "description": ""},
                            {"name": "lang", "type": "text", "required": False, "description": "dup"},
                        ], "layer": ""}],
        "relation_types": [],
        "relation_validity": [],
        "competency_questions": [],
        "regime": "soft",
    })
    errors = validate_schema(schema)
    assert any("twice" in e for e in errors)
