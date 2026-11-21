
import os
import re
import json
from urllib.parse import urlparse

import requests
from fastapi import FastAPI, HTTPException, Header, Depends
from pydantic import BaseModel, HttpUrl, Field
from typing import List

app = FastAPI(
    title="GPLinks Style URL Shortener API",
    description="URL shortener API powered by GPLinks",
    version="1.0.0"
)

# Environment variables
GPLINKS_API_KEY = os.getenv("GPLINKS_API_KEY", "").strip()
API_SECRET = os.getenv("API_SECRET", "").strip()

GPLINKS_ENDPOINT = "https://api.gplinks.com/st"
TIMEOUT = 30


# -----------------------------
# API Authentication
# -----------------------------

def verify_api_key(
    x_api_key: str = Header(default=None)
):
    if API_SECRET and x_api_key != API_SECRET:
        raise HTTPException(
            status_code=401,
            detail="Invalid or missing API key"
        )


# -----------------------------
# Request Models
# -----------------------------

class ShortenRequest(BaseModel):
    url: HttpUrl


class BulkRequest(BaseModel):
    urls: List[HttpUrl] = Field(min_length=1, max_length=100)


# -----------------------------
# URL Validation
# -----------------------------

def validate_url(url: str):
    parsed = urlparse(url)

    if parsed.scheme not in ("http", "https"):
        raise ValueError("Only HTTP and HTTPS URLs are supported")

    if not parsed.netloc:
        raise ValueError("Invalid destination URL")

    return url


# -----------------------------
# Extract Short URL
# -----------------------------

def extract_short_url(response, original_url):
    original_host = urlparse(original_url).netloc.lower()

    # 1. Check redirect response
    location = response.headers.get("Location")

    if location:
        parsed = urlparse(location)

        if (
            parsed.scheme in ("http", "https")
            and parsed.netloc.lower() != original_host
            and parsed.netloc.lower() != "api.gplinks.com"
        ):
            return location

    text = response.text.strip()

    # 2. Check JSON response
    try:
        data = response.json()

        def find_url(obj):
            if isinstance(obj, dict):
                # Check likely short URL fields first
                for key, value in obj.items():
                    key_lower = key.lower().replace("_", "").replace("-", "")

                    if (
                        isinstance(value, str)
                        and ("short" in key_lower or key_lower in ("link", "url"))
                    ):
                        candidate = value.strip()

                        if candidate.startswith(("http://", "https://")):
                            parsed = urlparse(candidate)

                            if (
                                parsed.netloc.lower() != original_host
                                and parsed.netloc.lower() != "api.gplinks.com"
                            ):
                                return candidate

                for value in obj.values():
                    result = find_url(value)
                    if result:
                        return result

            elif isinstance(obj, list):
                for item in obj:
                    result = find_url(item)
                    if result:
                        return result

            return None

        result = find_url(data)

        if result:
            return result

    except (ValueError, TypeError):
        pass

    # 3. Check plain text and HTML for URLs
    matches = re.findall(
        r'https?://[^\s"\'<>]+',
        text
    )

    for candidate in matches:
        candidate = candidate.rstrip(".,;)")
        parsed = urlparse(candidate)

        if (
            parsed.netloc
            and parsed.netloc.lower() != original_host
            and parsed.netloc.lower() != "api.gplinks.com"
        ):
            return candidate

    # 4. Check plain text containing only a short URL
    if text.startswith(("http://", "https://")):
        candidate = text.splitlines()[0].strip()
        parsed = urlparse(candidate)

        if (
            parsed.netloc
            and parsed.netloc.lower() != original_host
            and parsed.netloc.lower() != "api.gplinks.com"
        ):
            return candidate

    raise ValueError(
        "Could not extract short URL from GPLinks response. "
        f"HTTP status: {response.status_code}. "
        f"Response: {text[:500]}"
    )


# -----------------------------
# GPLinks Shortener
# -----------------------------

def gplinks_shorten(url: str):

    if not GPLINKS_API_KEY:
        raise ValueError(
            "GPLINKS_API_KEY is missing in Render environment variables"
        )

    url = validate_url(url)

    try:
        response = requests.get(
            GPLINKS_ENDPOINT,
            params={
                "api": GPLINKS_API_KEY,
                "url": url
            },
            headers={
                "User-Agent": "Mozilla/5.0 GPLinks-API/1.0"
            },
            timeout=TIMEOUT,
            allow_redirects=False
        )

        if response.status_code >= 400:
            raise ValueError(
                f"GPLinks HTTP error: {response.status_code}. "
                f"Response: {response.text[:500]}"
            )

        short_url = extract_short_url(response, url)

        return {
            "success": True,
            "original_url": url,
            "short_url": short_url,
            "provider": "gplinks"
        }

    except requests.Timeout:
        raise ValueError("GPLinks request timed out")

    except requests.RequestException as e:
        raise ValueError(f"GPLinks connection error: {str(e)}")


# -----------------------------
# API Homepage
# -----------------------------

@app.get("/")
def home():
    return {
        "success": True,
        "name": "GPLinks Style URL Shortener API",
        "version": "1.0.0",
        "provider": "gplinks",
        "endpoints": {
            "health": "/health",
            "shorten_get": "/shorten?url=YOUR_URL",
            "shorten_post": "/shorten",
            "bulk": "/bulk",
            "docs": "/docs"
        }
    }


# -----------------------------
# Health Check
# -----------------------------

@app.get("/health")
def health():
    return {
        "success": True,
        "status": "healthy",
        "provider": "gplinks",
        "api_key_configured": bool(GPLINKS_API_KEY)
    }


# -----------------------------
# GET Shorten Endpoint
# -----------------------------

@app.get("/shorten", dependencies=[Depends(verify_api_key)])
def shorten_get(url: str):

    try:
        return gplinks_shorten(url)

    except ValueError as e:
        raise HTTPException(
            status_code=502,
            detail=str(e)
        )


# -----------------------------
# POST Shorten Endpoint
# -----------------------------

@app.post("/shorten", dependencies=[Depends(verify_api_key)])
def shorten_post(request: ShortenRequest):

    try:
        return gplinks_shorten(str(request.url))

    except ValueError as e:
        raise HTTPException(
            status_code=502,
            detail=str(e)
        )


# -----------------------------
# BULK Shorten Endpoint
# -----------------------------

@app.post("/bulk", dependencies=[Depends(verify_api_key)])
def bulk_shorten(request: BulkRequest):

    results = []

    for url in request.urls:
        try:
            result = gplinks_shorten(str(url))
            results.append(result)

        except Exception as e:
            results.append({
                "success": False,
                "original_url": str(url),
                "error": str(e)
            })

    successful = sum(
        1 for item in results if item["success"]
    )

    return {
        "success": successful > 0,
        "total": len(results),
        "successful": successful,
        "failed": len(results) - successful,
        "results": results
    }


# -----------------------------
# Run locally
# -----------------------------

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=int(os.getenv("PORT", 8000))
    )
