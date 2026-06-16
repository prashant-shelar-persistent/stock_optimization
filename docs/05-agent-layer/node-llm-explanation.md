# Node: LLM Explanation

`llm_explanation_node` is the **final node** in the optimization pipeline. It generates a natural-language explanation of the optimization results using GPT-4o (via `langchain-openai`) when `OPENAI_API_KEY` is configured, or a deterministic template-based explanation as a fallback. The node is **non-fatal** — explanation failure produces a minimal fallback string rather than terminating the run.

**Source files:**
- Node: `backend/app/agents/nodes.py` — `llm_explanation_node()`
- Explainer: `backend/app/agents/explainer.py` — `generate_explanation()`
- Prompts: `backend/app/agents/prompts.py`

## Responsibility

```
llm_explanation_node
    └── generate_explanation(tickers, budget, classical_result, quantum_result,
                             comparison_summary, constraint_warnings)
            ├── Check OPENAI_API_KEY
            ├── [If set] _generate_llm_explanation() → GPT-4o via langchain-openai
            │       ├── Build prompt from _EXPLANATION_PROMPT template
            │       ├── ChatOpenAI(model="gpt-4o", temperature=0.3, max_tokens=400)
            │       └── Return LLM response content
            └── [If not set or LLM fails] _generate_template_explanation()
                    ├── Paragraph 1: Classical result summary
                    ├── Paragraph 2: Quantum comparison (if available)
                    └── Paragraph 3: Constraint warnings (if any)
```

## Node Signature

```python
def llm_explanation_node(state: AgentState) -> AgentState:
    """Generate a natural-language explanation of the optimization results."""
```

**Reads from state:** `tickers`, `budget`, `classical_result`, `quantum_result`, `comparison_summary`, `constraint_warnings`

**Writes to state:** `llm_explanation`, `node_timings_ms`, `completed_nodes`

**Fatal on failure:** **No** — any exception produces a minimal fallback string: `"Portfolio optimization completed. An explanation could not be generated at this time."`

## GPT-4o Prompt Construction

When `OPENAI_API_KEY` is set, the node builds a structured prompt from the `_EXPLANATION_PROMPT` template:

```python
_EXPLANATION_PROMPT = """\
You are a portfolio management expert. Explain the following portfolio \
optimization results to a non-technical investment professional in 2-3 \
concise paragraphs (≤ 250 words total).

Portfolio Universe: {tickers}
Budget: ${budget:,.0f}

Classical (Markowitz MVO) Result:
- Expected Return: {classical_return:.1%}
- Volatility: {classical_vol:.1%}
- Sharpe Ratio: {classical_sharpe:.3f}
- Number of Assets: {classical_num_assets}
- Top Holdings: {classical_top_holdings}

{quantum_section}

Comparison: {comparison_recommendation}

Constraint Warnings: {warnings}

Focus on:
1. What the classical optimizer recommends and why
2. How quantum optimization compares (if available)
3. Key risks or constraint trade-offs the investor should be aware of

Be specific, professional, and avoid jargon. Do not mention CVXPY, QAOA, \
VQE, LangGraph, or other technical implementation details. \
Do not use markdown formatting — plain text only.\
"""
```

### Prompt Variables

| Variable | Source | Example |
|---|---|---|
| `{tickers}` | `state["tickers"]` | `"AAPL, MSFT, GOOGL"` |
| `{budget}` | `state["budget"]` | `100000` → `"$100,000"` |
| `{classical_return}` | `classical_result["metrics"]["expected_return"]` | `0.123` → `"12.3%"` |
| `{classical_vol}` | `classical_result["metrics"]["volatility"]` | `0.098` → `"9.8%"` |
| `{classical_sharpe}` | `classical_result["metrics"]["sharpe_ratio"]` | `1.234` |
| `{classical_num_assets}` | `classical_result["metrics"]["num_assets"]` | `5` |
| `{classical_top_holdings}` | Top 3 weights by allocation | `"AAPL (32.1%), MSFT (28.4%), GOOGL (19.7%)"` |
| `{quantum_section}` | Built by `_build_quantum_section()` | QAOA/VQE metrics block |
| `{comparison_recommendation}` | `comparison_summary["recommendation"]` | Full recommendation string |
| `{warnings}` | `constraint_warnings` joined | `"min_return near maximum achievable"` |

### `langchain-openai` Integration

The LLM call uses `ChatOpenAI` from `langchain-openai`:

```python
from langchain_core.messages import HumanMessage
from langchain_openai import ChatOpenAI

llm = ChatOpenAI(
    model="gpt-4o",
    api_key=settings.OPENAI_API_KEY,
    temperature=0.3,
    max_tokens=400,
)

response = llm.invoke([HumanMessage(content=prompt)])
explanation = str(response.content).strip()
```

Key parameters:
- **Model:** `gpt-4o` (latest GPT-4o)
- **Temperature:** `0.3` (low randomness for consistent, professional output)
- **Max tokens:** `400` (≈ 300 words, enforces the ≤ 250 word guideline)

The prompt explicitly instructs the model to avoid technical jargon (CVXPY, QAOA, VQE, LangGraph) and to use plain text without markdown formatting.

## Template-Based Fallback

When `OPENAI_API_KEY` is empty or the LLM call fails, `_generate_template_explanation()` produces a deterministic explanation with up to three paragraphs:

### Paragraph 1: Classical Result Summary

Always present when `classical_result` is available:

```
The classical Markowitz Mean-Variance Optimization recommends a portfolio of
5 assets from the universe of AAPL, MSFT, GOOGL, AMZN, TSLA with an expected
annual return of 12.3% and volatility of 9.8% (Sharpe ratio: 1.234). The top
holdings are AAPL (32.1%), MSFT (28.4%), and GOOGL (19.7%).
```

### Paragraph 2: Quantum Comparison

Present when `comparison_summary` is available:

```
Quantum optimization (QAOA) outperforms classical by +0.087 Sharpe ratio
points (classical: 1.234, QAOA: 1.321). The quantum portfolio is recommended
for this asset universe.
```

If quantum ran but comparison failed, basic quantum metrics are included instead.

If quantum was not run:

```
Quantum optimization was not run for this configuration. Enable quantum
optimization to compare results against the classical baseline.
```

### Paragraph 3: Constraint Warnings

Present when `constraint_warnings` is non-empty (after filtering out internal quantum failure warnings):

```
Note: 1 constraint warning(s) were detected: min_return (0.185) is very close
to the maximum achievable return (0.190). Consider relaxing these constraints
if the results seem suboptimal.
```

## Fallback on Node Exception

If `generate_explanation()` raises an unexpected exception, the node catches it and returns a minimal fallback:

```python
except Exception as exc:
    logger.error("llm_explanation_failed", ...)
    explanation = (
        "Portfolio optimization completed. "
        "An explanation could not be generated at this time."
    )
    updated["llm_explanation"] = explanation
    return updated
```

## LLM Fallback on API Failure

If `OPENAI_API_KEY` is set but the GPT-4o call fails (network error, rate limit, invalid key), the explainer logs a warning and falls back to the template:

```python
if settings.OPENAI_API_KEY:
    try:
        return _generate_llm_explanation(...)
    except Exception as exc:
        logger.warning("llm_explanation_failed_falling_back", error=str(exc), ...)

return _generate_template_explanation(...)
```

This two-level fallback ensures the explanation is always populated, even in degraded environments.

## Output Format

The explanation is always:
- **Plain text** — no markdown, no bullet points, no headers
- **Concise** — 2–3 paragraphs, ≤ 300 words
- **Professional** — suitable for display in a financial dashboard
- **Jargon-free** — no mention of CVXPY, QAOA, VQE, LangGraph, or other implementation details

## Related Pages

- [Agent State](agent-state.md) — Full state field reference
- [Node: Comparison](node-comparison.md) — Provides `comparison_summary`
- [Node: Frontier Computation](node-frontier.md) — Runs before LLM explanation (conditional)
- [Graph Definition](graph-definition.md) — LLM explanation is the final node before END
