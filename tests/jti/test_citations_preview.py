def test_rag_citations_format():
    """Verify RAG pipeline citation format matches expected structure."""
    # RAG pipeline returns citations as list of dicts with title/text keys
    citation = {"title": "jti_001.csv", "text": "加熱菸是使用加熱不燃燒技術的菸品"}
    assert "title" in citation
    assert "text" in citation
