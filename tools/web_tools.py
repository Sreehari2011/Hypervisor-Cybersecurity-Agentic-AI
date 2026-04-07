import requests
import json
import urllib3
from langchain_core.tools import tool

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

@tool
def web_search_osint(query: str):
    """
    Performs a web search to gather OSINT (Open Source Intelligence).
    Useful for finding vulnerabilities, exploits, or target info.
    """
    try:
        from duckduckgo_search import DDGS
        results = DDGS().text(keywords=query, max_results=5)
        if not results:
            return "No results found."
        
        formatted = "\n".join([f"- {r['title']}: {r['href']}\n  {r['body']}" for r in results])
        return formatted
    except ImportError:
        return "Error: duckduckgo-search library not installed. Run `pip install duckduckgo-search`"
    except Exception as e:
        return f"Search Error: {e}"

@tool
def retrieve_url_content(url: str):
    """Fetches the raw HTML/Text content of a URL (using curl)."""
    import subprocess
    try:
        result = subprocess.run(["curl", "-L", "--max-time", "10", url], 
            capture_output=True, 
            text=True
        )
        return result.stdout[:5000]
    except Exception as e:
        return f"Curl Error: {e}"

@tool
def advanced_http_request(method: str, url: str, data: str = None, headers: str = None, cookies: str = None, allow_redirects: bool = True):
    """
    Makes precise HTTP requests (GET, POST, PUT, etc.) to interact with Web Forms, APIs, and Admin Portals.
    Crucial for bypassing Web UIs where `curl` via shell becomes too complex or fails to maintain sessions.
    
    Args:
        method: "GET" or "POST"
        url: The target URL (must use domain if VHost mapped)
        data: JSON string of the payload data/form-data (e.g., '{"username": "admin", "password": "password"}')
        headers: JSON string of headers (e.g., '{"Content-Type": "application/x-www-form-urlencoded"}')
        cookies: JSON string of cookies to send (e.g., '{"session": "123456"}')
    """
    try:
        kwargs = {"allow_redirects": allow_redirects, "timeout": 15, "verify": False}
        
        if data:
            try:
                kwargs["data"] = json.loads(data)
            except Exception:
                kwargs["data"] = data
        
        if headers:
            kwargs["headers"] = json.loads(headers)
        if cookies:
            kwargs["cookies"] = json.loads(cookies)
            
        response = requests.request(method.upper(), url, **kwargs)
        
        result = {
            "status_code": response.status_code,
            "headers": dict(response.headers),
            "cookies": dict(response.cookies),
            "body_snippet": response.text[:5000]
        }
        return json.dumps(result, indent=2)
    except Exception as e:
        return f"HTTP Request Failed: {str(e)}"