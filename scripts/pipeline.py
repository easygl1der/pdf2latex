"""
LangGraph pipeline 构建
"""

from langgraph.graph import StateGraph, END, START

from .config import PipelineState
from .nodes import (
    classifier_node, route_by_doc_type,
    supervisor_node, dispatch_chapters, chapter_writer_node,
    retriever_node, assembler_node,
    paper_writer_node,
    compiler_node,
    ref_manager_node,
)


def build_graph():
    g = StateGraph(PipelineState)

    g.add_node("classifier",     classifier_node)
    g.add_node("supervisor",     supervisor_node)
    g.add_node("chapter_writer", chapter_writer_node)
    g.add_node("retriever",      retriever_node)
    g.add_node("ref_manager",    ref_manager_node)
    g.add_node("assembler",      assembler_node)
    g.add_node("paper_writer",   paper_writer_node)
    g.add_node("compiler",       compiler_node)

    g.add_edge(START, "classifier")
    g.add_conditional_edges("classifier", route_by_doc_type, ["supervisor", "paper_writer"])

    # book 路径
    g.add_conditional_edges("supervisor", dispatch_chapters, ["chapter_writer"])
    g.add_edge("chapter_writer", "retriever")
    g.add_edge("retriever", "ref_manager")
    g.add_edge("ref_manager", "assembler")
    g.add_edge("assembler", "compiler")

    # paper 路径
    g.add_edge("paper_writer", "compiler")

    g.add_edge("compiler", END)

    return g.compile()
