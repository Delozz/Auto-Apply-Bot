"""
Unit tests for vision form analyzer and adaptive filler merge logic.
These tests cover pure logic — no Playwright browser, no LLM calls.
"""
import pytest
from app.utils.validators import FormField, FormManifest
from app.automation.adaptive_filler import merge_manifest_with_dom
from datetime import datetime


def make_manifest(fields: list[dict]) -> FormManifest:
    return FormManifest(
        url="https://example.com/apply",
        fields=[FormField(**f) for f in fields],
        analyzed_at=datetime.utcnow().isoformat(),
    )


# ─── FormField / FormManifest model tests ────────────────────────────────────

def test_form_field_defaults():
    f = FormField(label="First Name", field_type="text")
    assert f.required is False
    assert f.options == []
    assert f.placeholder == ""
    assert f.selector_hint == ""
    assert f.section == ""


def test_form_manifest_creation():
    manifest = make_manifest([
        {"label": "Gender", "field_type": "select", "options": ["Male", "Female", "Non-binary"]},
        {"label": "Email", "field_type": "text"},
    ])
    assert manifest.url == "https://example.com/apply"
    assert len(manifest.fields) == 2
    assert manifest.fields[0].options == ["Male", "Female", "Non-binary"]


# ─── merge_manifest_with_dom tests ───────────────────────────────────────────

def test_merge_enriches_options():
    """Manifest options override empty DOM options for matching label."""
    dom_fields = [{"type": "select", "label": "Gender", "selector": "#gender", "options": []}]
    manifest = make_manifest([
        {"label": "Gender", "field_type": "select", "options": ["Male", "Female", "Non-binary"]}
    ])
    merged = merge_manifest_with_dom(dom_fields, manifest)
    assert len(merged) == 1
    assert merged[0]["options"] == ["Male", "Female", "Non-binary"]


def test_merge_case_insensitive_label_matching():
    """Labels matched case-insensitively."""
    dom_fields = [{"type": "text", "label": "first name", "selector": "#fn"}]
    manifest = make_manifest([{"label": "First Name", "field_type": "text"}])
    merged = merge_manifest_with_dom(dom_fields, manifest)
    assert len(merged) == 1


def test_merge_adds_manifest_only_fields():
    """Fields in manifest but not in DOM are appended."""
    dom_fields = [{"type": "text", "label": "Email", "selector": "#email"}]
    manifest = make_manifest([
        {"label": "Email", "field_type": "text"},
        {"label": "Work Authorization", "field_type": "select", "options": ["Yes", "No"]},
    ])
    merged = merge_manifest_with_dom(dom_fields, manifest)
    assert len(merged) == 2
    work_auth = next(f for f in merged if f["label"] == "Work Authorization")
    assert work_auth["options"] == ["Yes", "No"]


def test_merge_does_not_duplicate_dom_fields():
    """DOM fields that match manifest are not duplicated."""
    dom_fields = [
        {"type": "text", "label": "First Name", "selector": "#fn"},
        {"type": "text", "label": "Last Name", "selector": "#ln"},
    ]
    manifest = make_manifest([{"label": "First Name", "field_type": "text"}])
    merged = merge_manifest_with_dom(dom_fields, manifest)
    assert len(merged) == 2


def test_merge_preserves_dom_options_when_manifest_empty():
    """If manifest has no options, DOM options are preserved."""
    dom_fields = [{"type": "select", "label": "Country", "selector": "#country",
                   "options": ["USA", "Canada"]}]
    manifest = make_manifest([{"label": "Country", "field_type": "select", "options": []}])
    merged = merge_manifest_with_dom(dom_fields, manifest)
    # Manifest has empty options — DOM options should stay
    assert merged[0]["options"] == ["USA", "Canada"]


def test_merge_empty_dom_empty_manifest():
    """Both empty — returns empty list."""
    merged = merge_manifest_with_dom([], make_manifest([]))
    assert merged == []


def test_merge_required_flag_propagated():
    """Manifest required=True is applied to DOM field."""
    dom_fields = [{"type": "text", "label": "Phone", "selector": "#phone"}]
    manifest = make_manifest([{"label": "Phone", "field_type": "text", "required": True}])
    merged = merge_manifest_with_dom(dom_fields, manifest)
    assert merged[0].get("required") is True


# ─── analyze_page_screenshot JSON parsing ────────────────────────────────────

def test_form_field_type_values():
    """All documented field_type values are accepted by the model."""
    valid_types = ["text", "textarea", "select", "react_select", "checkbox", "radio", "file"]
    for ft in valid_types:
        f = FormField(label="Test", field_type=ft)
        assert f.field_type == ft
