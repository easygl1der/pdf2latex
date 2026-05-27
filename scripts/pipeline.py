from langgraph.graph import StateGraph, END
from .nodes import (
    PipelineState, classifier_node, skeleton_node,
    dispatch_chapters, chapter_writer_node, assembler_node, compiler_node
)

def build_graph():
    workflow = StateGraph(PipelineState)

    # 1. Classify document
    workflow.add_node("classifier", classifier_node)
    # 2. Build Skeleton
    workflow.add_node("skeleton", skeleton_node)
    # 3. Write individual chapters (parallel)
    workflow.add_node("chapter_writer", chapter_writer_node)
    # 4. Assemble by surgical injection
    workflow.add_node("assembler", assembler_node)
    # 5. Compile
    workflow.add_node("compiler", compiler_node)

    # Define edges
    workflow.set_entry_point("classifier")
    workflow.add_edge("classifier", "skeleton")
    
    # Use Send API for dynamic parallelism
    workflow.add_conditional_edges("skeleton", dispatch_chapters, ["chapter_writer"])
    
    workflow.add_edge("chapter_writer", "assembler")
    workflow.add_edge("assembler", "compiler")
    workflow.add_edge("compiler", END)

    return workflow.compile()
