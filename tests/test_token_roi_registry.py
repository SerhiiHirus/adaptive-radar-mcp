"""Unit tests for Token ROI Registry and vendor optimization benchmark matching."""

from adaptive_radar_mcp.evaluator.token_roi_registry import TokenROIRegistry


def test_token_roi_anthropic_prompt_caching():
    text = "Implemented Anthropic prompt caching support with cache_control block."
    benchmarks = TokenROIRegistry.match_benchmarks(text)
    assert len(benchmarks) >= 1
    names = [b.feature_name for b in benchmarks]
    assert any("Anthropic Prompt Caching" in n for n in names)
    urls = [b.vendor_doc_url for b in benchmarks]
    assert any("docs.anthropic.com" in u for u in urls)


def test_token_roi_structured_outputs():
    text = "Native structured output generation using response_format and json_schema."
    benchmarks = TokenROIRegistry.match_benchmarks(text)
    assert len(benchmarks) >= 1
    assert any("OpenAI Structured Outputs" in b.feature_name for b in benchmarks)


def test_token_roi_local_embeddings():
    text = "Switched to fastembed for local embedding generation on CPU."
    benchmarks = TokenROIRegistry.match_benchmarks(text)
    assert len(benchmarks) >= 1
    assert any("FastEmbed Local Embedding" in b.feature_name for b in benchmarks)


def test_token_roi_neutral_text():
    text = "Fixed minor documentation typo in README."
    benchmarks = TokenROIRegistry.match_benchmarks(text)
    assert len(benchmarks) == 0
