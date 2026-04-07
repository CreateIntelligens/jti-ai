from app.services.jti.main_agent import MainAgent


def test_jti_file_search_citations_include_chunk_text():
    agent = MainAgent()

    context = type(
        "RetrievedContext",
        (),
        {
            "uri": "",
            "title": "jti_001.csv",
            "text": 'q,a\n"什麼是加熱菸?","加熱菸是..."',
        },
    )()
    chunk = type("Chunk", (), {"retrieved_context": context})()
    grounding_metadata = type("GroundingMetadata", (), {"grounding_chunks": [chunk]})()
    candidate = type("Candidate", (), {"grounding_metadata": grounding_metadata})()
    response = type("Response", (), {"candidates": [candidate]})()

    citations = agent._extract_file_search_citations(response)

    assert citations == [
        {
            "uri": "",
            "title": "jti_001.csv",
            "text": 'q,a\n"什麼是加熱菸?","加熱菸是..."',
        }
    ]
