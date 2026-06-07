import json

from ankicli.notetypes import export_notetype_bundle, load_notetype_bundle, summarize_notetype_changes


def sample_notetype():
    return {
        "id": 123,
        "name": "Basic",
        "type": 0,
        "sortf": 0,
        "css": ".card { font-family: arial; }",
        "flds": [
            {"name": "Front", "ord": 0, "font": "Arial"},
            {"name": "Back", "ord": 1, "font": "Arial"},
        ],
        "tmpls": [
            {
                "name": "Card 1",
                "ord": 0,
                "qfmt": "{{Front}}",
                "afmt": "{{FrontSide}}<hr id=answer>{{Back}}",
            },
            {
                "name": "Reverse",
                "ord": 1,
                "qfmt": "{{Back}}",
                "afmt": "{{Front}}",
            },
        ],
    }


def test_notetype_export_uses_directory_bundle_for_fields_templates_and_css(tmp_path):
    export_notetype_bundle(sample_notetype(), tmp_path)

    assert json.loads((tmp_path / "notetype.json").read_text())["name"] == "Basic"
    assert json.loads((tmp_path / "fields.json").read_text())[0]["name"] == "Front"
    assert (tmp_path / "style.css").read_text() == ".card { font-family: arial; }"
    assert (tmp_path / "templates" / "00-Card_1" / "front.html").read_text() == "{{Front}}"
    assert (tmp_path / "templates" / "01-Reverse" / "back.html").read_text() == "{{Front}}"


def test_notetype_bundle_round_trips_multiple_card_templates(tmp_path):
    original = sample_notetype()
    export_notetype_bundle(original, tmp_path)

    loaded = load_notetype_bundle(tmp_path)

    assert loaded["flds"] == original["flds"]
    assert loaded["tmpls"] == original["tmpls"]
    assert loaded["css"] == original["css"]


def test_notetype_change_summary_detects_schema_changes(tmp_path):
    old = sample_notetype()
    export_notetype_bundle(old, tmp_path)
    fields_path = tmp_path / "fields.json"
    fields = json.loads(fields_path.read_text())
    fields.append({"name": "Extra", "ord": 2, "font": "Arial"})
    fields_path.write_text(json.dumps(fields))

    new = load_notetype_bundle(tmp_path)
    summary = summarize_notetype_changes(old, new)

    assert summary.schema_change is True
    assert "added field Extra" in summary.messages
