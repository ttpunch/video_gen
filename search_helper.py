import os
import json
import requests
from dotenv import load_dotenv

load_dotenv()

OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")

def clean_json_response(resp_text: str) -> str:
    """Strip markdown code fences (like ```json ... ```) from LLM response text."""
    resp_text = resp_text.strip()
    if resp_text.startswith("```"):
        lines = resp_text.splitlines()
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        resp_text = "\n".join(lines).strip()
    return resp_text

def classify_need_for_search(prompt: str, ollama_model: str) -> dict:
    """Ask the local LLM if the given topic needs factual web search grounding."""
    url = f"{OLLAMA_HOST}/api/generate"
    
    system_prompt = (
        "You are an expert fact-checking classifier. "
        "Your task is to determine whether the user's video topic requires real-world facts, scientific data, "
        "recent news, or historical accuracy. "
        "Creative prompts (e.g. self-help, fictional stories, general motivation, poetry) do NOT need search. "
        "Respond ONLY with a valid JSON object matching this exact format, with no markdown styling, no conversational filler, and no extra text:\n"
        "{\n"
        "  \"requires_search\": true or false,\n"
        "  \"search_query\": \"A concise Google search query to find the key facts, or empty string if search is not needed\"\n"
        "}"
    )
    
    full_prompt = f"System: {system_prompt}\nUser: Topic: {prompt}"
    
    payload = {
        "model": ollama_model,
        "prompt": full_prompt,
        "stream": False,
        "format": "json"
    }
    
    try:
        response = requests.post(url, json=payload, timeout=20)
        if response.status_code == 200:
            resp_text = response.json().get("response", "").strip()
            cleaned = clean_json_response(resp_text)
            data = json.loads(cleaned)
            if "requires_search" in data:
                return data
    except Exception as e:
        print(f"Error checking if search is needed: {e}")
        
    return {"requires_search": False, "search_query": ""}

def search_duckduckgo(query: str, max_results: int = 5) -> str:
    """Query DuckDuckGo for search snippets using the duckduckgo_search library."""
    try:
        from duckduckgo_search import DDGS
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=max_results))
            if not results:
                return ""
            
            snippets = []
            for idx, r in enumerate(results):
                title = r.get("title", "No Title")
                body = r.get("body", "")
                snippets.append(f"[{idx+1}] Source: {title}\nContent: {body}")
            return "\n\n".join(snippets)
    except Exception as e:
        print(f"DuckDuckGo search error: {e}")
        return ""

def search_tavily(query: str, api_key: str, max_results: int = 5) -> str:
    """Query Tavily API for search snippets."""
    url = "https://api.tavily.com/search"
    payload = {
        "api_key": api_key,
        "query": query,
        "max_results": max_results,
        "search_depth": "basic"
    }
    try:
        response = requests.post(url, json=payload, timeout=15)
        if response.status_code == 200:
            results = response.json().get("results", [])
            snippets = []
            for idx, r in enumerate(results):
                title = r.get("title", "No Title")
                content = r.get("content", "")
                snippets.append(f"[{idx+1}] Source: {title}\nContent: {content}")
            return "\n\n".join(snippets)
    except Exception as e:
        print(f"Tavily search error: {e}")
        return ""

def search_google(query: str, api_key: str, cse_id: str, max_results: int = 5) -> str:
    """Query Google Custom Search API for snippets."""
    url = "https://www.googleapis.com/customsearch/v1"
    params = {
        "key": api_key,
        "cx": cse_id,
        "q": query,
        "num": max_results
    }
    try:
        response = requests.get(url, params=params, timeout=15)
        if response.status_code == 200:
            items = response.json().get("items", [])
            snippets = []
            for idx, item in enumerate(items):
                title = item.get("title", "No Title")
                snippet = item.get("snippet", "")
                snippets.append(f"[{idx+1}] Source: {title}\nContent: {snippet}")
            return "\n\n".join(snippets)
    except Exception as e:
        print(f"Google Search error: {e}")
        return ""

def get_web_grounding_context(prompt: str, ollama_model: str) -> dict:
    """Dynamically checks if search is needed, runs the search using the best available provider, and returns context."""
    classification = classify_need_for_search(prompt, ollama_model)
    
    if not classification.get("requires_search") or not classification.get("search_query"):
        return {
            "requires_search": False,
            "search_query": "",
            "context": ""
        }
    
    query = classification["search_query"]
    print(f"Web search required for: '{prompt}'. Running query: '{query}'")
    
    # Check for Tavily API key
    tavily_key = os.getenv("TAVILY_API_KEY")
    google_key = os.getenv("GOOGLE_SEARCH_API_KEY")
    google_cse = os.getenv("GOOGLE_CSE_ID")
    
    context = ""
    if tavily_key:
        context = search_tavily(query, tavily_key)
    elif google_key and google_cse:
        context = search_google(query, google_key, google_cse)
    
    # Fallback to DuckDuckGo if premium APIs are not configured or failed
    if not context:
        context = search_duckduckgo(query)
        
    return {
        "requires_search": True,
        "search_query": query,
        "context": context
    }
