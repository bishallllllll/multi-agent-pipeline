import asyncio
import httpx
import json

async def test_query():
    url = "http://localhost:8000/query"
    payload = {
        "query": "EURUSD strategies",
        "file_id": "test_123",
        "k": 1
    }
    
    print(f"--- TESTING RAG API CONNECTION ---")
    print(f"Target: {url}")
    print(f"Query: {payload['query']}")
    
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(url, json=payload, timeout=10.0)
            
            if response.status_code == 200:
                results = response.json()
                print(f"Status: SUCCESS (200)")
                
                if not results:
                    print("Result: No matches found.")
                    return

                # Format like the proposed method
                output = "RELEVANT DATABASE EXCERPTS:\n"
                for i, res in enumerate(results):
                    doc, score = res
                    relevance = 1 - score
                    content = doc.get('page_content', 'N/A')
                    output += f"\n[{i+1}] (Relevance: {relevance:.2f})\nContent: {content}\n"
                
                print(output)
            else:
                print(f"Status: FAILED ({response.status_code})")
                print(f"Error: {response.text}")
                
    except Exception as e:
        print(f"Status: CONNECTION ERROR")
        print(f"Error details: {str(e)}")

if __name__ == "__main__":
    asyncio.run(test_query())
