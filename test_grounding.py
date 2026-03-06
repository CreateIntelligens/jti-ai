import asyncio
from dotenv import load_dotenv

load_dotenv()

from app.services.gemini_clients import init_registry, get_client_for_store
from app.services.gemini_service import init_gemini_client
import os
from google.genai import types

async def main():
    init_registry()
    init_gemini_client()
    
    # Try searching
    query = "傑太日煙的加熱菸叫什麼名字？"
    language = "zh"
    store_env_key = f"JTI_STORE_ID_{language.upper()}"
    store_id = os.getenv(store_env_key) or os.getenv("JTI_STORE_ID_ZH")
    store_name = f"fileSearchStores/{store_id}"
    
    client = get_client_for_store(store_name)
    response = client.models.generate_content(
        model="gemini-2.5-flash-lite",
        contents=query,
        config=types.GenerateContentConfig(
            tools=[
                types.Tool(
                    file_search=types.FileSearch(
                        file_search_store_names=[store_name]
                    )
                )
            ],
            thinking_config=types.ThinkingConfig(thinking_budget=0),
        ),
    )
    print("Response text:", response.text)
    if response.candidates:
        cand = response.candidates[0]
        if cand.grounding_metadata:
            print("Found grounding_metadata!")
            chunks = cand.grounding_metadata.grounding_chunks
            supports = cand.grounding_metadata.grounding_supports
            print(f"Chunks: {len(chunks) if chunks else 0}")
            print(f"Supports: {len(supports) if supports else 0}")
            if chunks:
                for c in chunks:
                    if c.retrieved_context:
                        print("URI:", c.retrieved_context.uri, "TITLE:", c.retrieved_context.title)
        else:
            print("No grounding metadata.")

if __name__ == "__main__":
    asyncio.run(main())
