from pathlib import Path
from typing import Any, Optional


class CollectionError(RuntimeError):
    pass


class AnkiCollectionService:
    def __init__(self, collection: Any):
        self.collection = collection

    @classmethod
    def open(cls, collection_path: Path) -> "AnkiCollectionService":
        try:
            from anki.collection import Collection
        except ModuleNotFoundError as exc:
            raise CollectionError("the anki package is required for collection operations") from exc
        if not collection_path.exists():
            raise CollectionError("collection not found: %s" % collection_path)
        return cls(Collection(str(collection_path)))

    def close(self) -> None:
        close = getattr(self.collection, "close", None)
        if callable(close):
            close()

    def list_decks(self) -> dict[str, Any]:
        decks = getattr(self.collection, "decks")
        if hasattr(decks, "all_names_and_ids"):
            values = decks.all_names_and_ids()
            result = [{"id": int(item.id), "name": str(item.name)} for item in values]
        elif hasattr(decks, "all"):
            result = [{"id": int(item["id"]), "name": str(item["name"])} for item in decks.all()]
        else:
            raise CollectionError("unsupported Anki deck manager")
        return {"decks": result}

    def deck_info(self, name: str) -> dict[str, Any]:
        deck = self.collection.decks.by_name(name)
        if not deck:
            raise CollectionError("deck not found: %s" % name)
        return {"deck": deck}

    def create_deck(self, name: str) -> dict[str, Any]:
        deck_id = self.collection.decks.id(name)
        return {"changed_ids": [int(deck_id)]}

    def rename_deck(self, old: str, new: str) -> dict[str, Any]:
        deck = self.collection.decks.by_name(old)
        if not deck:
            raise CollectionError("deck not found: %s" % old)
        self.collection.decks.rename(deck, new)
        return {"changed_ids": [int(deck["id"])]}

    def delete_deck(self, name: str) -> dict[str, Any]:
        deck = self.collection.decks.by_name(name)
        if not deck:
            raise CollectionError("deck not found: %s" % name)
        self.collection.decks.remove([deck["id"]])
        return {"changed_ids": [int(deck["id"])]}

    def delete_filtered_deck(self, name: str) -> dict[str, Any]:
        deck = self._filtered_deck_by_name(name)
        self.collection.decks.remove([deck["id"]])
        return {"changed_ids": [int(deck["id"])]}

    def list_filtered_decks(self) -> dict[str, Any]:
        return {
            "filtered_decks": [
                self._serialize_filtered_deck(deck)
                for deck in self.collection.decks.all()
                if deck.get("dyn")
            ]
        }

    def get_filtered_deck(self, name: str) -> dict[str, Any]:
        deck = self._filtered_deck_by_name(name)
        return self._serialize_filtered_deck(deck)

    def filtered_deck_order_labels(self) -> dict[str, Any]:
        labels = list(self.collection.sched.filtered_deck_order_labels())
        orders = [
            {"name": name, "value": value, "label": labels[value] if value < len(labels) else name}
            for name, value in _FILTERED_ORDER_VALUES.items()
        ]
        return {"orders": orders}

    def create_or_update_filtered_deck(
        self,
        name: str,
        *,
        search: str,
        limit: int,
        order: str,
        reschedule: bool,
        allow_empty: bool,
        create: bool,
    ) -> dict[str, Any]:
        deck = self.collection.decks.by_name(name)
        if deck and not deck.get("dyn"):
            raise CollectionError("deck exists but is not a filtered deck: %s" % name)
        if not deck:
            if not create:
                raise CollectionError("filtered deck not found: %s" % name)
            deck_id = int(self.collection.decks.new_filtered(name))
        else:
            deck_id = int(deck["id"])

        filtered = self.collection.sched.get_or_create_filtered_deck(deck_id)
        _set_attr_or_item(filtered, "id", deck_id)
        _set_attr_or_item(filtered, "name", name)
        _set_attr_or_item(filtered, "allow_empty", allow_empty)
        config = _get_attr_or_item(filtered, "config")
        _set_attr_or_item(config, "reschedule", reschedule)
        _replace_search_terms(
            _get_attr_or_item(config, "search_terms"),
            search=search,
            limit=limit,
            order=_filtered_order_value(order),
        )
        output = self.collection.sched.add_or_update_filtered_deck(filtered)
        changed_id = int(getattr(output, "id", deck_id) or deck_id)
        return {"changed_ids": [changed_id]}

    def rebuild_filtered_deck(self, name: str) -> dict[str, Any]:
        deck = self._filtered_deck_by_name(name)
        deck_id = int(deck["id"])
        output = self.collection.sched.rebuild_filtered_deck(deck_id)
        result = {"changed_ids": [deck_id]}
        count = getattr(output, "count", None)
        if count is not None:
            result["count"] = int(count)
        return result

    def empty_filtered_deck(self, name: str) -> dict[str, Any]:
        deck = self._filtered_deck_by_name(name)
        deck_id = int(deck["id"])
        self.collection.sched.empty_filtered_deck(deck_id)
        return {"changed_ids": [deck_id]}

    def search_notes(self, query: str) -> dict[str, Any]:
        return {"note_ids": [int(note_id) for note_id in self.collection.find_notes(query)]}

    def get_note(self, note_id: int) -> dict[str, Any]:
        note = self.collection.get_note(note_id)
        fields = dict(note.items()) if hasattr(note, "items") else {}
        tags_attr = getattr(note, "tags", [])
        tags = tags_attr() if callable(tags_attr) else tags_attr
        return {"id": int(getattr(note, "id", note_id)), "fields": fields, "tags": list(tags)}

    def create_note(self, *, notetype: str, deck: str, fields: dict[str, str], tags: list[str]) -> dict[str, Any]:
        model = self._model_by_name(notetype)
        note = self.collection.new_note(model)
        for key, value in fields.items():
            note[key] = value
        note.tags = tags
        deck_id = self.collection.decks.id(deck)
        self.collection.add_note(note, deck_id)
        return {"changed_ids": [int(note.id)]}

    def update_note(self, note_id: int, *, fields: dict[str, str], tags: Optional[list[str]] = None) -> dict[str, Any]:
        note = self.collection.get_note(note_id)
        for key, value in fields.items():
            note[key] = value
        if tags is not None:
            note.tags = tags
        self.collection.update_note(note)
        return {"changed_ids": [int(note.id)]}

    def delete_note(self, note_id: int) -> dict[str, Any]:
        self.collection.remove_notes([note_id])
        return {"changed_ids": [int(note_id)]}

    def search_cards(self, query: str) -> dict[str, Any]:
        return {"card_ids": [int(card_id) for card_id in self.collection.find_cards(query)]}

    def get_card(self, card_id: int) -> dict[str, Any]:
        card = self.collection.get_card(card_id)
        return {
            "id": int(getattr(card, "id", card_id)),
            "note_id": int(getattr(card, "nid", 0)),
            "deck_id": int(getattr(card, "did", 0)),
            "queue": int(getattr(card, "queue", 0)),
            "type": int(getattr(card, "type", 0)),
            "due": int(getattr(card, "due", 0)),
        }

    def suspend_cards(self, query: str) -> dict[str, Any]:
        card_ids = [int(card_id) for card_id in self.collection.find_cards(query)]
        self._scheduler_call("suspend_cards", card_ids)
        return {"changed_ids": card_ids}

    def unsuspend_cards(self, query: str) -> dict[str, Any]:
        card_ids = [int(card_id) for card_id in self.collection.find_cards(query)]
        self._scheduler_call("unsuspend_cards", card_ids)
        return {"changed_ids": card_ids}

    def list_notetypes(self) -> dict[str, Any]:
        models = self.collection.models.all()
        return {
            "notetypes": [
                {
                    "id": int(model.get("id")),
                    "name": model.get("name"),
                    "fields": [field.get("name") for field in model.get("flds", [])],
                    "templates": [template.get("name") for template in model.get("tmpls", [])],
                }
                for model in models
            ]
        }

    def get_notetype(self, name: str) -> dict[str, Any]:
        model = self._model_by_name(name)
        return dict(model)

    def update_notetype(self, name: str, model: dict[str, Any]) -> dict[str, Any]:
        existing = self._model_by_name(name)
        model = dict(model)
        model["id"] = existing["id"]
        model["name"] = existing["name"]
        self.collection.models.update_dict(model, skip_checks=False)
        return {"changed_ids": [int(existing["id"])]}

    def _model_by_name(self, name: str) -> dict[str, Any]:
        by_name = getattr(self.collection.models, "by_name", None)
        model: Optional[dict[str, Any]] = by_name(name) if callable(by_name) else None
        if model is None:
            for candidate in self.collection.models.all():
                if candidate.get("name") == name:
                    model = candidate
                    break
        if model is None:
            raise CollectionError("notetype not found: %s" % name)
        return model

    def _scheduler_call(self, method_name: str, card_ids: list[int]) -> None:
        method = getattr(getattr(self.collection, "sched"), method_name, None)
        if not callable(method):
            raise CollectionError("scheduler does not support %s" % method_name)
        method(card_ids)

    def _filtered_deck_by_name(self, name: str) -> dict[str, Any]:
        deck = self.collection.decks.by_name(name)
        if not deck:
            raise CollectionError("filtered deck not found: %s" % name)
        if not deck.get("dyn"):
            raise CollectionError("deck is not a filtered deck: %s" % name)
        return deck

    @staticmethod
    def _serialize_filtered_deck(deck: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": int(deck["id"]),
            "name": deck["name"],
            "search_terms": _legacy_search_terms(deck),
            "reschedule": bool(deck.get("resched", deck.get("reschedule", False))),
        }


_FILTERED_ORDER_VALUES = {
    "OLDEST_REVIEWED_FIRST": 0,
    "RANDOM": 1,
    "INTERVALS_ASCENDING": 2,
    "INTERVALS_DESCENDING": 3,
    "LAPSES": 4,
    "ADDED": 5,
    "DUE": 6,
    "REVERSE_ADDED": 7,
    "RETRIEVABILITY_ASCENDING": 8,
    "RETRIEVABILITY_DESCENDING": 9,
}


def _filtered_order_value(order: str) -> int:
    normalized = order.strip().upper().replace("-", "_")
    if normalized not in _FILTERED_ORDER_VALUES:
        raise CollectionError("unknown filtered deck order: %s" % order)
    return _FILTERED_ORDER_VALUES[normalized]


def _legacy_search_terms(deck: dict[str, Any]) -> list[dict[str, Any]]:
    terms = []
    for term in deck.get("terms", []):
        if isinstance(term, (list, tuple)):
            terms.append(
                {
                    "search": term[0] if len(term) > 0 else "",
                    "limit": int(term[1]) if len(term) > 1 else 0,
                    "order": int(term[2]) if len(term) > 2 else 0,
                }
            )
        elif isinstance(term, dict):
            terms.append(
                {
                    "search": term.get("search", ""),
                    "limit": int(term.get("limit", 0)),
                    "order": int(term.get("order", 0)),
                }
            )
    return terms


def _get_attr_or_item(obj: Any, name: str) -> Any:
    if isinstance(obj, dict):
        return obj[name]
    return getattr(obj, name)


def _set_attr_or_item(obj: Any, name: str, value: Any) -> None:
    if isinstance(obj, dict):
        obj[name] = value
    else:
        setattr(obj, name, value)


def _replace_search_terms(search_terms: Any, *, search: str, limit: int, order: int) -> None:
    if hasattr(search_terms, "clear"):
        search_terms.clear()
    else:
        del search_terms[:]
    if hasattr(search_terms, "add"):
        term = search_terms.add()
        term.search = search
        term.limit = limit
        term.order = order
    else:
        search_terms.append({"search": search, "limit": limit, "order": order})
