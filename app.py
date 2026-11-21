
import requests
import re
from urllib.parse import urlparse, urljoin
from bs4 import BeautifulSoup


def extract_short_url(response, original_url):
    original = urlparse(original_url)

    # Check HTTP redirect first
    location = response.headers.get("Location")

    if location:
        location = urljoin(response.url, location)
        parsed = urlparse(location)

        if parsed.netloc and parsed.netloc.lower() != original.netloc.lower():
            if parsed.netloc.lower() != "api.gplinks.com":
                return location

    # Check JSON
    try:
        data = response.json()

        if isinstance(data, dict):
            for key in (
                "short_url", "shortlink", "short",
                "link", "url", "shortenedUrl"
            ):
                value = data.get(key)

                if isinstance(value, str) and value.startswith("http"):
                    parsed = urlparse(value)

                    if parsed.netloc.lower() != original.netloc.lower():
                        return value
    except (ValueError, TypeError):
        pass

    # Parse HTML
    soup = BeautifulSoup(response.text, "html.parser")

    # Check actual links, excluding forms and scripts
    for tag in soup.find_all(["a"]):
        href = tag.get("href")

        if not href:
            continue

        candidate = urljoin(response.url, href)
        parsed = urlparse(candidate)

        if (
            parsed.scheme in ("http", "https")
            and parsed.netloc.lower() != original.netloc.lower()
            and parsed.netloc.lower() != "api.gplinks.com"
        ):
            return candidate

    # Check plain text URLs
    matches = re.findall(
        r'https?://[^\s"\'<>]+',
        soup.get_text(" ", strip=True)
    )

    for candidate in matches:
        candidate = candidate.rstrip(".,;)")
        parsed = urlparse(candidate)

        if (
            parsed.netloc
            and parsed.netloc.lower() != original.netloc.lower()
            and parsed.netloc.lower() != "api.gplinks.com"
        ):
            return candidate

    return None


def gplinks_shorten(url: str):
    if not GPLINKS_API_KEY:
        raise ValueError("GPLINKS_API_KEY is missing")

    session = requests.Session()

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/130.0.0.0 Safari/537.36"
        )
    }

    # STEP 1: Request GPLinks form
    first = session.get(
        "https://api.gplinks.com/st",
        params={
            "api": GPLINKS_API_KEY,
            "url": url
        },
        headers=headers,
        timeout=30,
        allow_redirects=True
    )

    if first.status_code >= 400:
        raise ValueError(
            f"GPLinks GET failed: HTTP {first.status_code}"
        )

    # Check if GET already returned the short link
    short_url = extract_short_url(first, url)

    if short_url:
        return {
            "success": True,
            "original_url": url,
            "short_url": short_url,
            "provider": "gplinks"
        }

    # STEP 2: Parse the HTML form
    soup = BeautifulSoup(first.text, "html.parser")
    form = soup.find("form", id="quick-link")

    if not form:
        raise ValueError(
            "GPLinks did not return the expected quick-link form"
        )

    action = form.get("action")

    if not action:
        raise ValueError("GPLinks form action is missing")

    post_url = urljoin(first.url, action)

    # Collect hidden form fields, including CSRF token
    form_data = {}

    for field in form.find_all("input"):
        name = field.get("name")

        if name:
            form_data[name] = field.get("value", "")

    # STEP 3: Submit the form with the same session/cookies
    post_headers = {
        **headers,
        "Referer": first.url,
        "Origin": "https://api.gplinks.com",
        "Content-Type": "application/x-www-form-urlencoded"
    }

    second = session.post(
        post_url,
        data=form_data,
        headers=post_headers,
        timeout=30,
        allow_redirects=False
    )

    if second.status_code >= 400:
        raise ValueError(
            f"GPLinks form submission failed: HTTP {second.status_code}"
        )

    # STEP 4: Extract final short URL
    short_url = extract_short_url(second, url)

    if short_url:
        return {
            "success": True,
            "original_url": url,
            "short_url": short_url,
            "provider": "gplinks"
        }

    # Follow a redirect if GPLinks returned one
    if second.is_redirect:
        location = second.headers.get("Location")

        if location:
            short_url = urljoin(second.url, location)
            parsed = urlparse(short_url)

            if (
                parsed.netloc
                and parsed.netloc.lower()
                != urlparse(url).netloc.lower()
                and parsed.netloc.lower() != "api.gplinks.com"
            ):
                return {
                    "success": True,
                    "original_url": url,
                    "short_url": short_url,
                    "provider": "gplinks"
                }

    raise ValueError(
        "GPLinks form was submitted, but no short URL was returned. "
        f"HTTP status: {second.status_code}. "
        "Check GPLinks response and form submission."
    )
