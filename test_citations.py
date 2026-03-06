import asyncio
import os
from dotenv import load_dotenv

os.environ["GEMINI_API_KEYS"] = "POC:REDACTED_KEY_POC,JTI傑太日煙:REDACTED_KEY_JTI,護聯HCIOT:REDACTED_KEY_HCIOT"
load_dotenv()

from app.services.gemini_clients import init_registry
from app.services.gemini_service import init_gemini_client
from app.services.jti.main_agent import main_agent

async def main():
    init_registry()
    init_gemini_client()
    query = "Ploom有出哪些顏色？"
    language = "zh"
    
    kb_text, citations = await main_agent._file_search(query, language)
    print("Text length:", len(kb_text) if kb_text else 0)
    print("Citations output:", citations)

if __name__ == "__main__":
    asyncio.run(main())
