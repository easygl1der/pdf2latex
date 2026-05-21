"""
LangGraph pipeline 构建
"""

from langgraph.graph import StateGraph, END, START

from .config import PipelineState
from .nodes import supervisor_node, dispatch_chapters, chapter_writer_node, retriever_node, assembler_node


def build_graph():
    g = StateGraph(PipelineState)
    g.add_node("supervisor",     supervisor_node)
    g.add_node("chapter_writer", chapter_writer_node)
    g.add_node("retriever",      retriever_node)
    g.add_node("assembler",      assembler_node)

    g.add_edge(START, "supervisor")
    g.add_conditional_edges("supervisor", dispatch_chapters, ["chapter_writer"])
    g.add_edge("chapter_writer", "retriever")
    g.add_edge("retriever", "assembler")
    g.add_edge("assembler", END)
    return g.compile()
