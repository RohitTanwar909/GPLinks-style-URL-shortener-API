import os
import re
import json
from urllib.parse import urlparse

import requests
from fastapi import FastAPI, HTTPException, Header, Query
from pydantic import BaseModel, HttpUrl

app = FastAPI(title="GPLinks Wrapper API", version="1.0.0")

GPLINKS_API_KEY = os.getenv("GPLINKS_API_KEY", "").strip()
API_SECRET = os.getenv("API_SECRET", "").strip()  # optional: protects your Render API
GPLINKS_ENDPOINT = "https://api.gplinks.com/st"
TIMEOUT_SECONDS = int(os.getenv("REQUEST_TIMEOUT", "20"))

class ShortenRequest(BaseModel):
    url: HttpUrl
class BulkRequest(BaseModel):
    urls: list[HttpUrl]


def auth_check(x_api_key: str | None):
    if API_SECRET and x_api_key != API_SECRET:
        raise HTTPException(status_code=401, detail="Invalid API key")


def validate_destination(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise HTTPException(status_code=400, detail="Only valid http/https URLs are allowed")
    return url


def extract_short_url(response: requests.Response) -> str | None:
    # GPLinks response formats may vary. Check redirect Location, JSON fields, then text URL.
    location = response.headers.get("Location")
    if location and "gplinks" in location.lower():
        return location

    body = response.text.strip()
    try:
        data = response.json()
        if isinstance(data, dict):
            for key in ("short_url", "shortlink", "short", "url", "link"):
                value = data.get(key)
                if isinstance(value, str) and value.startswith(("http://", "https://")):
                    return value
            # Return useful provider error messages if present
            if data.get("error") or data.get("message"):
                raise HTTPException(status_code=502, detail=f"GPLinks response: {data.get('error') or data.get('message')}")
    except ValueError:
        pass


    # Look for a URL in plain-text/HTML response
    matches = re.findall(r'https?://[^\s"\'<>]+', body)
    for candidate in matches:
        candidate = candidate.rstrip(".,;)")
        if "gplinks" in candidate.lower():
            return candidate
    if body.startswith("http://") or body.startswith("https://"):
        return body.splitlines()[0].strip()
    return None



def shorten_one(destination: str) -> dict:
    if not GPLINKS_API_KEY:
        raise HTTPException(status_code=500, detail="Render environment variable GPLINKS_API_KEY is not set")
    destination = validate_destination(str(destination))
    try:
        # Do not follow redirects: if provider returns a redirect, capture its Location.
        res = requests.get(
            GPLINKS_ENDPOINT,
            params={"api": GPLINKS_API_KEY, "url": destination},
            timeout=TIMEOUT_SECONDS,
            allow_redirects=False,
            headers={"User-Agent": "GPLinks-Wrapper/1.0"},
        )
    except requests.RequestException as exc:
        raise HTTPException(status_code=502, detail=f"Could not connect to GPLinks: {exc.__class__.__name__}")

    if res.status_code >= 400:
        raise HTTPException(status_code=502, detail=f"GPLinks returned HTTP {res.status_code}")
    short_url = extract_short_url(res)
    if not short_url:
        raise HTTPException(status_code=502, detail="Could not parse short link from GPLinks response. Check GPLinks API key or provider response format.")
    return {"success": True, "original_url": destination, "short_url": short_url, "provider": "gplinks"}



@app.get("/")
def root():
    return {"name": "GPLinks Wrapper API", "status": "online", "endpoints": ["GET /health", "GET /shorten?url=...", "POST /shorten", "POST /bulk"]}



@app.get("/health")
def health():
    return {"success": True, "status": "healthy"}



@app.get("/shorten")
def shorten_get(url: HttpUrl = Query(...), x_api_key: str | None = Header(default=None)):
    auth_check(x_api_key)
    return shorten_one(str(url))



@app.post("/shorten")
def shorten_post(payload: ShortenRequest, x_api_key: str | None = Header(default=None)):
    auth_check(x_api_key)
    return shorten_one(str(payload.url))



@app.post("/bulk")
def shorten_bulk(payload: BulkRequest, x_api_key: str | None = Header(default=None)):
    auth_check(x_api_key)
    if not payload.urls:
        raise HTTPException(status_code=400, detail="Provide at least one URL")
    if len(payload.urls) > 50:
        raise HTTPException(status_code=400, detail="Maximum 50 URLs per request")
    results = []
    for url in payload.urls:
        try:
            results.append(shorten_one(str(url)))
        except HTTPException as exc:
            results.append({"success": False, "original_url": str(url), "error": exc.detail})
    return {"success": all(item.get("success") for item in results), "count": len(results), "results": results}
