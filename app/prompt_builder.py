def build_prompt(question: str, memories: list[str]):

    context = "\n".join(
        f"- {memory}" for memory in memories
    )

    return f"""
You are Memoria.

Context:
{context}

Question:
{question}

Use the context when relevant.
"""