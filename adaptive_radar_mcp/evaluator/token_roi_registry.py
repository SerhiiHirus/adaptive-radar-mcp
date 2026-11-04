"""Registry of verifiable LLM/AI optimization patterns with vendor citations."""

from dataclasses import dataclass


@dataclass(frozen=True)
class OptimizationBenchmark:
    """Documented vendor benchmark for LLMOps cost reduction."""

    pattern_id: str
    feature_name: str
    vendor_doc_url: str
    cost_mechanism: str
    measured_impact: str


KNOWN_OPTIMIZATIONS: list[OptimizationBenchmark] = [
    OptimizationBenchmark(
        pattern_id="anthropic_prompt_caching",
        feature_name="Anthropic Prompt Caching (cache_control)",
        vendor_doc_url="https://docs.anthropic.com/en/docs/build-with-claude/prompt-caching",
        cost_mechanism="Cached prompt tokens billed at 10% of base input cost (up to 90% discount).",
        measured_impact="Reduces prompt token cost by up to 90% on static prompts (>1024 tokens).",
    ),
    OptimizationBenchmark(
        pattern_id="openai_structured_outputs",
        feature_name="OpenAI Structured Outputs (json_schema strict)",
        vendor_doc_url="https://openai.com/index/introducing-structured-outputs-in-the-api/",
        cost_mechanism="Enforces 100% adherence to schema via constrained decoding, eliminating retry cycles.",
        measured_impact="Eliminates retry loops and validation tokens caused by malformed JSON.",
    ),
    OptimizationBenchmark(
        pattern_id="gemini_context_caching",
        feature_name="Google Gemini Context Caching",
        vendor_doc_url="https://ai.google.dev/gemini-api/docs/caching",
        cost_mechanism="Re-uses large input contexts (>32k tokens) across consecutive requests at reduced pricing.",
        measured_impact="Cuts input token pricing significantly on long documents and repeated contexts.",
    ),
    OptimizationBenchmark(
        pattern_id="litellm_semantic_cache",
        feature_name="LiteLLM Proxy / Semantic Caching",
        vendor_doc_url="https://docs.litellm.ai/docs/proxy/caching",
        cost_mechanism="In-memory or Redis caching of identical or semantically similar completions.",
        measured_impact="Reduces external LLM API calls and tokens to zero for repeated queries.",
    ),
    OptimizationBenchmark(
        pattern_id="fastembed_local_embeddings",
        feature_name="FastEmbed Local Embedding Generation",
        vendor_doc_url="https://qdrant.github.io/fastembed/",
        cost_mechanism="Runs quantised ONNX embedding models locally on CPU without remote API calls.",
        measured_impact="100% reduction in embedding API tokens and per-token pricing.",
    ),
]


class TokenROIRegistry:
    """Matches release content against verified vendor optimization benchmarks."""

    @classmethod
    def match_benchmarks(cls, text: str) -> list[OptimizationBenchmark]:
        """Inspect text for verifiable vendor optimization features."""
        lower = text.lower()
        matched: list[OptimizationBenchmark] = []

        if "prompt cache" in lower or "cache_control" in lower:
            matched.append(KNOWN_OPTIMIZATIONS[0])
        if "structured output" in lower or "json_schema" in lower or "response_format" in lower:
            matched.append(KNOWN_OPTIMIZATIONS[1])
        if "context cache" in lower or "cached content" in lower:
            matched.append(KNOWN_OPTIMIZATIONS[2])
        if "semantic cache" in lower or "redis cache" in lower:
            matched.append(KNOWN_OPTIMIZATIONS[3])
        if "fastembed" in lower or "local embedding" in lower or "onnx" in lower:
            matched.append(KNOWN_OPTIMIZATIONS[4])

        return matched
