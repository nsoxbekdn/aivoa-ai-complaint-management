"""The LangGraph StateGraph that drives the whole analysis.

    START
      → prepare_input
      → extract_complaint_fields
      → validate_extraction
            ├─ invalid & retries left → repair_extraction → validate_extraction
            └─ valid / out of retries → assess_completeness
      → classify_risk
      → generate_summary
      → generate_recommendations
      → assemble_result
      → END

Why a graph instead of one big function: each node has one small prompt and one small
contract, the retry loop is an explicit edge rather than a hidden `while`, and a partial
failure (LLM down) degrades node-by-node instead of failing the whole request.
"""

from __future__ import annotations

from functools import lru_cache

from langgraph.graph import END, START, StateGraph

from app.graph.nodes import (
    assemble_result,
    assess_completeness_node,
    classify_risk,
    extract_complaint_fields,
    generate_recommendations,
    generate_summary,
    prepare_input,
    repair_extraction,
    route_after_validation,
    validate_extraction,
)
from app.graph.state import GraphState, initial_state
from app.schemas.analysis import (
    ComplaintAnalysisResponse,
    ComplaintRecommendations,
    CompletenessAssessment,
    ExtractedComplaintFields,
    RiskAssessment,
)
from app.services.completeness import assess_completeness


def build_graph():
    """Wire the nodes together. Kept separate from `run_analysis` so tests can inspect it."""
    graph = StateGraph(GraphState)

    graph.add_node("prepare_input", prepare_input)
    graph.add_node("extract_complaint_fields", extract_complaint_fields)
    graph.add_node("validate_extraction", validate_extraction)
    graph.add_node("repair_extraction", repair_extraction)
    graph.add_node("assess_completeness", assess_completeness_node)
    graph.add_node("classify_risk", classify_risk)
    graph.add_node("generate_summary", generate_summary)
    graph.add_node("generate_recommendations", generate_recommendations)
    graph.add_node("assemble_result", assemble_result)

    graph.add_edge(START, "prepare_input")
    graph.add_edge("prepare_input", "extract_complaint_fields")
    graph.add_edge("extract_complaint_fields", "validate_extraction")

    # The one conditional edge in the workflow: repair at most `max_extraction_retries` times.
    graph.add_conditional_edges(
        "validate_extraction",
        route_after_validation,
        {"repair_extraction": "repair_extraction", "assess_completeness": "assess_completeness"},
    )
    graph.add_edge("repair_extraction", "validate_extraction")

    graph.add_edge("assess_completeness", "classify_risk")
    graph.add_edge("classify_risk", "generate_summary")
    graph.add_edge("generate_summary", "generate_recommendations")
    graph.add_edge("generate_recommendations", "assemble_result")
    graph.add_edge("assemble_result", END)

    return graph.compile()


@lru_cache
def get_compiled_graph():
    """Compile once per process — compilation is pure setup work."""
    return build_graph()


def build_finalization_graph():
    """Analysis-only graph for an edited, authoritative complaint form."""
    graph = StateGraph(GraphState)
    graph.add_node("assess_completeness", assess_completeness_node)
    graph.add_node("classify_risk", classify_risk)
    graph.add_node("generate_summary", generate_summary)
    graph.add_node("generate_recommendations", generate_recommendations)
    graph.add_node("assemble_result", assemble_result)
    graph.add_edge(START, "assess_completeness")
    graph.add_edge("assess_completeness", "classify_risk")
    graph.add_edge("classify_risk", "generate_summary")
    graph.add_edge("generate_summary", "generate_recommendations")
    graph.add_edge("generate_recommendations", "assemble_result")
    graph.add_edge("assemble_result", END)
    return graph.compile()


@lru_cache
def get_compiled_finalization_graph():
    return build_finalization_graph()


def run_analysis(
    raw_text: str,
    *,
    input_type: str = "text",
    filename: str | None = None,
    warnings: list[str] | None = None,
) -> ComplaintAnalysisResponse:
    """Run the workflow and map the final state onto the API response schema."""
    final: GraphState = get_compiled_graph().invoke(
        initial_state(raw_text, input_type, filename, warnings or [])
    )

    return ComplaintAnalysisResponse(
        extracted_fields=final.get("extracted_fields") or ExtractedComplaintFields(),
        completeness=final.get("completeness") or CompletenessAssessment(),
        risk_assessment=final.get("risk_assessment") or RiskAssessment(),
        summary=final.get("summary", ""),
        recommendations=final.get("recommendations") or ComplaintRecommendations(),
        # dict.fromkeys keeps order while removing duplicates from repeated node warnings.
        warnings=list(dict.fromkeys(final.get("warnings", []))),
        original_text=final.get("raw_text", ""),
        input_filename=final.get("filename"),
    )


def run_final_analysis(
    fields: ExtractedComplaintFields,
    canonical_text: str,
    *,
    warnings: list[str] | None = None,
) -> ComplaintAnalysisResponse:
    """Regenerate QA support from the final form without re-extracting its values."""
    state = initial_state(canonical_text, "final_form", None, warnings or [])
    state.update(
        {
            "extracted_fields": fields,
            "extraction_valid": True,
        }
    )
    final: GraphState = get_compiled_finalization_graph().invoke(state)
    final_fields = final.get("extracted_fields") or fields
    final_completeness = assess_completeness(final_fields)
    summary = final.get("summary", "")
    required_summary_facts: list[str] = []
    if fields.manufacturing_date and fields.manufacturing_date.isoformat() not in summary:
        required_summary_facts.append(
            f"manufacturing date {fields.manufacturing_date.isoformat()}"
        )
    if fields.expiry_date and fields.expiry_date.isoformat() not in summary:
        required_summary_facts.append(f"expiry date {fields.expiry_date.isoformat()}")
    if required_summary_facts:
        summary = (
            summary.rstrip().rstrip(".")
            + ". Product dates: "
            + "; ".join(required_summary_facts)
            + "."
        ).lstrip()

    return ComplaintAnalysisResponse(
        extracted_fields=final_fields,
        completeness=final_completeness,
        risk_assessment=final.get("risk_assessment") or RiskAssessment(),
        summary=summary,
        recommendations=final.get("recommendations") or ComplaintRecommendations(),
        warnings=list(dict.fromkeys(final.get("warnings", []))),
        original_text=canonical_text,
    )
