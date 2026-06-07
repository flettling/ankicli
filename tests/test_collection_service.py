from ankicli.collection import AnkiCollectionService


class FakeScheduler:
    def __init__(self):
        self.suspended = []
        self.unsuspended = []
        self.filtered = {}
        self.rebuilt = []
        self.emptied = []

    def suspend_cards(self, card_ids):
        self.suspended.extend(card_ids)
        return {"count": len(card_ids)}

    def unsuspend_cards(self, card_ids):
        self.unsuspended.extend(card_ids)
        return {"count": len(card_ids)}

    def filtered_deck_order_labels(self):
        return ["Oldest seen first", "Random"]

    def get_or_create_filtered_deck(self, deck_id):
        deck = self.filtered.get(deck_id)
        if deck is None:
            deck = FakeFilteredDeck(deck_id)
            self.filtered[deck_id] = deck
        return deck

    def add_or_update_filtered_deck(self, deck):
        self.filtered[deck.id] = deck
        return FakeOp(id=deck.id)

    def rebuild_filtered_deck(self, deck_id):
        self.rebuilt.append(deck_id)
        return FakeOp(count=3)

    def empty_filtered_deck(self, deck_id):
        self.emptied.append(deck_id)
        return FakeOp()


class FakeOp:
    def __init__(self, id=None, count=None):
        self.id = id
        self.count = count


class FakeSearchTerms(list):
    def add(self):
        term = FakeSearchTerm()
        self.append(term)
        return term


class FakeSearchTerm:
    def __init__(self):
        self.search = ""
        self.limit = 0
        self.order = 0


class FakeFilteredConfig:
    def __init__(self):
        self.reschedule = False
        self.search_terms = FakeSearchTerms()


class FakeFilteredDeck:
    def __init__(self, deck_id):
        self.id = deck_id
        self.name = ""
        self.config = FakeFilteredConfig()
        self.allow_empty = False


class FakeNote:
    id = 42

    def items(self):
        return [("Front", "question"), ("Back", "answer")]

    def tags(self):
        return ["tag"]


class FakeModels:
    def __init__(self):
        self.updated = None
        self.models = [
            {
                "id": 1,
                "name": "Basic",
                "flds": [{"name": "Front"}, {"name": "Back"}],
                "tmpls": [{"name": "Card 1", "qfmt": "{{Front}}", "afmt": "{{Back}}"}],
                "css": ".card{}",
            }
        ]

    def all(self):
        return self.models

    def by_name(self, name):
        return self.models[0] if name == "Basic" else None

    def update_dict(self, model, skip_checks=False):
        self.updated = (model, skip_checks)


class FakeCollection:
    def __init__(self):
        self.sched = FakeScheduler()
        self.models = FakeModels()
        self.decks = FakeDecks()

    def find_notes(self, query):
        return [42] if query == "front:question" else []

    def get_note(self, note_id):
        assert note_id == 42
        return FakeNote()

    def find_cards(self, query):
        return [100, 101] if query == "is:new" else []


class FakeDecks:
    def __init__(self):
        self.decks = {
            "Filtered": {"id": 9, "name": "Filtered", "dyn": True, "terms": [["is:due", 100, 0]], "resched": True},
            "Normal": {"id": 10, "name": "Normal", "dyn": False},
        }
        self.next_id = 20

    def all(self):
        return list(self.decks.values())

    def by_name(self, name):
        return self.decks.get(name)

    def new_filtered(self, name):
        deck_id = self.next_id
        self.next_id += 1
        self.decks[name] = {"id": deck_id, "name": name, "dyn": True}
        return deck_id


def test_collection_service_searches_notes_and_serializes_fields():
    service = AnkiCollectionService(FakeCollection())

    assert service.search_notes("front:question") == {"note_ids": [42]}
    assert service.get_note(42)["fields"] == {"Front": "question", "Back": "answer"}


def test_collection_service_suspends_cards_by_search_query():
    collection = FakeCollection()
    service = AnkiCollectionService(collection)

    result = service.suspend_cards("is:new")

    assert collection.sched.suspended == [100, 101]
    assert result["changed_ids"] == [100, 101]


def test_collection_service_updates_notetype_with_anki_model_manager():
    collection = FakeCollection()
    service = AnkiCollectionService(collection)
    model = dict(collection.models.models[0])
    model["css"] = ".card{color:red}"

    result = service.update_notetype("Basic", model)

    assert result == {"changed_ids": [1]}
    assert collection.models.updated == (model, False)


def test_collection_service_lists_and_reads_filtered_decks():
    service = AnkiCollectionService(FakeCollection())

    assert service.list_filtered_decks()["filtered_decks"] == [
        {
            "id": 9,
            "name": "Filtered",
            "search_terms": [{"search": "is:due", "limit": 100, "order": 0}],
            "reschedule": True,
        }
    ]
    assert service.get_filtered_deck("Filtered")["name"] == "Filtered"


def test_collection_service_creates_filtered_deck_via_scheduler_config():
    collection = FakeCollection()
    service = AnkiCollectionService(collection)

    result = service.create_or_update_filtered_deck(
        "Agent Filter",
        search="deck:Ankizin is:due",
        limit=50,
        order="RANDOM",
        reschedule=False,
        allow_empty=True,
        create=True,
    )

    deck_id = result["changed_ids"][0]
    filtered = collection.sched.filtered[deck_id]
    assert filtered.name == "Agent Filter"
    assert filtered.allow_empty is True
    assert filtered.config.reschedule is False
    assert filtered.config.search_terms[0].search == "deck:Ankizin is:due"
    assert filtered.config.search_terms[0].limit == 50
    assert filtered.config.search_terms[0].order == 1


def test_collection_service_rebuilds_and_empties_filtered_deck():
    collection = FakeCollection()
    service = AnkiCollectionService(collection)

    rebuilt = service.rebuild_filtered_deck("Filtered")
    emptied = service.empty_filtered_deck("Filtered")

    assert collection.sched.rebuilt == [9]
    assert collection.sched.emptied == [9]
    assert rebuilt == {"changed_ids": [9], "count": 3}
    assert emptied == {"changed_ids": [9]}


def test_collection_service_delete_filtered_deck_refuses_normal_deck():
    service = AnkiCollectionService(FakeCollection())

    try:
        service.delete_filtered_deck("Normal")
    except Exception as exc:
        assert "not a filtered deck" in str(exc)
    else:
        raise AssertionError("expected normal deck deletion to be rejected")
