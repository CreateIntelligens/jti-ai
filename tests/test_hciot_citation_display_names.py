from app.services.hciot.main_agent import HciotMainAgent


def test_localize_citations_uses_display_name(monkeypatch):
    fake_store = type(
        "FakeStore",
        (),
        {
            "list_files": lambda self, language: [
                {"name": "prp.csv", "display_name": "PRP.csv"},
                {"name": "helicobacter_pylori.csv", "display_name": "幽門螺旋桿菌.csv"},
            ]
        },
    )()

    monkeypatch.setattr(
        "app.services.hciot.main_agent.get_hciot_knowledge_store",
        lambda: fake_store,
    )

    citations = [
        {"title": "prp.csv", "uri": ""},
        {"title": "Reference", "uri": "file:///tmp/helicobacter_pylori.csv"},
        {"title": "Unmapped", "uri": ""},
    ]

    localized = HciotMainAgent._localize_citations("zh", citations)

    assert localized == [
        {"title": "PRP.csv", "uri": ""},
        {"title": "幽門螺旋桿菌.csv", "uri": "file:///tmp/helicobacter_pylori.csv"},
        {"title": "Unmapped", "uri": ""},
    ]
