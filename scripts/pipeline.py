"""
LangGraph Pipeline Construction
"""

from langgraph.graph import StateGraph, END, START

from .config import PipelineState
from .nodes import (
    classifier_node, route_by_doc_type,
    supervisor_node, dispatch_chapters, chapter_writer_node,
    validator_node,
    assembler_node,
    paper_writer_node,
    paper_validator_node,
    compiler_node,
)


def build_graph():
    g = StateGraph(PipelineState)

    g.add_node("classifier",      classifier_node)
    g.add_node("supervisor",      supervisor_node)
    g.add_node("chapter_writer",  chapter_writer_node)
    g.add_node("validator",       validator_node)
    g.add_node("assembler",       assembler_node)
    g.add_node("paper_writer",    paper_writer_node)
    g.add_node("paper_validator", paper_validator_node)
    g.add_node("compiler",        compiler_node)

    g.add_edge(START, "classifier")
    g.add_conditional_edges("classifier", route_by_doc_type, ["supervisor", "paper_writer"])

    # Book path
    g.add_conditional_edges("supervisor", dispatch_chapters, ["chapter_writer"])
    g.add_edge("chapter_writer", "validator")
    g.add_edge("validator", "assembler")
    g.add_edge("assembler", "compiler")

    # Paper path
    g.add_edge("paper_writer", "paper_validator")
    g.add_edge("paper_validator", "compiler")

    g.add_edge("compiler", END)

    return g.compile()
