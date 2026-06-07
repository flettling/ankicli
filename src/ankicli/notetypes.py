import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any


def export_notetype_bundle(notetype: dict[str, Any], destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    metadata = {key: value for key, value in notetype.items() if key not in {"flds", "tmpls", "css"}}
    (destination / "notetype.json").write_text(_json(metadata))
    (destination / "fields.json").write_text(_json(notetype.get("flds", [])))
    (destination / "style.css").write_text(str(notetype.get("css", "")))

    templates_dir = destination / "templates"
    templates_dir.mkdir(exist_ok=True)
    for index, template in enumerate(notetype.get("tmpls", [])):
        template_dir = templates_dir / ("%02d-%s" % (index, _safe_name(str(template.get("name", "template")))))
        template_dir.mkdir(parents=True, exist_ok=True)
        template_meta = {key: value for key, value in template.items() if key not in {"qfmt", "afmt"}}
        (template_dir / "template.json").write_text(_json(template_meta))
        (template_dir / "front.html").write_text(str(template.get("qfmt", "")))
        (template_dir / "back.html").write_text(str(template.get("afmt", "")))


def load_notetype_bundle(source: Path) -> dict[str, Any]:
    metadata = json.loads((source / "notetype.json").read_text())
    fields = json.loads((source / "fields.json").read_text())
    css = (source / "style.css").read_text()
    templates = []
    templates_root = source / "templates"
    for template_dir in sorted(path for path in templates_root.iterdir() if path.is_dir()):
        template = json.loads((template_dir / "template.json").read_text())
        template["qfmt"] = (template_dir / "front.html").read_text()
        template["afmt"] = (template_dir / "back.html").read_text()
        templates.append(template)
    result = dict(metadata)
    result["flds"] = fields
    result["tmpls"] = templates
    result["css"] = css
    return result


@dataclass(frozen=True)
class NotetypeChangeSummary:
    messages: list[str]
    schema_change: bool


def summarize_notetype_changes(old: dict[str, Any], new: dict[str, Any]) -> NotetypeChangeSummary:
    messages: list[str] = []
    old_fields = [field.get("name") for field in old.get("flds", [])]
    new_fields = [field.get("name") for field in new.get("flds", [])]
    for name in new_fields:
        if name not in old_fields:
            messages.append("added field %s" % name)
    for name in old_fields:
        if name not in new_fields:
            messages.append("removed field %s" % name)

    old_templates = [template.get("name") for template in old.get("tmpls", [])]
    new_templates = [template.get("name") for template in new.get("tmpls", [])]
    for name in new_templates:
        if name not in old_templates:
            messages.append("added template %s" % name)
    for name in old_templates:
        if name not in new_templates:
            messages.append("removed template %s" % name)

    if old.get("css") != new.get("css"):
        messages.append("changed css")

    schema_change = old_fields != new_fields or old_templates != new_templates
    return NotetypeChangeSummary(messages=messages, schema_change=schema_change)


def _safe_name(name: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", name).strip("_")
    return safe or "template"


def _json(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
