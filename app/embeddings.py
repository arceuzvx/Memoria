import os
from google import genai

client = genai.Client(
    api_key=os.getenv("GEMINI_API_KEY")
)

MODEL = "gemini-embedding-001"

def embed_text(text: str):
    response = client.models.embed_content(
        model=MODEL,
        contents=text
    )

    return response.embeddings[0].values

def vector_size():
    return len(embed_text("hello"))