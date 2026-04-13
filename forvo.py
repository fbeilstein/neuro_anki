"""
Forvo pronunciation scraper — standalone module.
Extracted from anki_forvo_dl addon, stripped of Anki/Qt dependencies.
"""

import base64
import os
import re
import urllib.parse
import cloudscraper
from dataclasses import dataclass, field
from typing import List, Optional


SEARCH_URL = "https://forvo.com/word/"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)
HEADERS = [
    ('User-Agent', USER_AGENT),
    ('Accept', 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8'),
    ('Accept-Language', 'en-US,en;q=0.5'),
    ('Referer', 'https://forvo.com/'),
]


@dataclass
class ForvoPronunciation:
    """A single pronunciation result from Forvo."""
    word: str
    language: str
    user: str
    origin: str
    votes: int
    download_url: str
    is_ogg: bool
    forvo_id: int


def _get_scraper():
    """Create a cloudscraper instance to bypass CloudFlare."""
    return cloudscraper.create_scraper(
        browser={
            'browser': 'chrome',
            'platform': 'windows',
            'desktop': True
        }
    )


def search_forvo(word: str, language: str) -> List[ForvoPronunciation]:
    """
    Scrape Forvo for pronunciations of a word in the given language.

    Args:
        word: The word to search for (e.g. "Haus")
        language: Forvo language code (e.g. "de", "ja", "pl")

    Returns:
        List of ForvoPronunciation objects, sorted by votes descending.
    """
    scraper = _get_scraper()

    query = urllib.parse.quote_plus(word.strip())
    url = SEARCH_URL + query

    response = scraper.get(url)
    if response.status_code == 404:
        return []
    response.raise_for_status()
    page = response.text

    from bs4 import BeautifulSoup
    soup = BeautifulSoup(page, "html.parser")

    # Find all language containers
    lang_containers = soup.find_all(id=re.compile(r"language-container-\w{2,4}"))
    available = {
        re.findall(r"language-container-(\w{2,4})", el.attrs["id"])[0]: el
        for el in lang_containers
    }

    if language not in available:
        return []

    container = available[language]
    results = []

    for accents in container.find_all(class_="pronunciations"):
        for pron_list in accents.find_all(class_="pronunciations-list"):
            for li in pron_list.find_all("li"):
                more = li.find_all(class_="more")
                if not more:
                    continue

                # Extract vote count
                try:
                    vote_el = more[0].find(class_="main_actions")
                    rate_el = vote_el.find(id=re.compile(r"word_rate_\d+"))
                    num_votes_el = rate_el.find(class_="num_votes")
                    inner_spans = num_votes_el.find_all("span")
                    if inner_spans:
                        votes = int(re.findall(r"(-?\d+)", inner_spans[0].get_text())[0])
                    else:
                        votes = 0
                except Exception:
                    votes = 0

                # Extract audio URL from Play() onclick
                try:
                    play_el = li.find(id=re.compile(r"play_\d+"))
                    onclick = play_el.attrs.get("onclick", "")

                    # Try MP3 first (4th argument in Play())
                    mp3_matches = re.findall(
                        r"Play\(\d+,'.+','.+',\w+,'([^']+)", onclick
                    )
                    is_ogg = False
                    if mp3_matches:
                        decoded = base64.b64decode(mp3_matches[0]).decode("utf-8")
                        dl_url = "https://audio00.forvo.com/audios/mp3/" + decoded
                    else:
                        # Fallback to OGG (3rd argument)
                        ogg_matches = re.findall(
                            r"Play\(\d+,'[^']+','([^']+)", onclick
                        )
                        if not ogg_matches:
                            continue
                        decoded = base64.b64decode(ogg_matches[0]).decode("utf-8")
                        dl_url = "https://audio00.forvo.com/ogg/" + decoded
                        is_ogg = True
                except Exception:
                    continue

                # Extract username
                try:
                    info_el = li.find(
                        lambda el: bool(el.find_all(string=re.compile("Pronunciation by"))),
                        class_="info",
                    )
                    username = re.findall(
                        r"Pronunciation by(.*)", info_el.get_text(" "), re.S
                    )[0].strip()
                except Exception:
                    username = "unknown"

                # Extract origin (country/region)
                try:
                    origin = li.find(class_="from").contents[0]
                except Exception:
                    origin = ""

                # Extract Forvo pronunciation ID
                try:
                    forvo_id = next(iter({
                        int(v) for link in li.find_all(class_="ofLink")
                        for k, v in link.attrs.items()
                        if re.match(r"^data-p\d+$", k) and re.match(r"^\d+$", v)
                    }))
                except (StopIteration, ValueError):
                    forvo_id = 0

                results.append(ForvoPronunciation(
                    word=word.strip(),
                    language=language,
                    user=username,
                    origin=str(origin),
                    votes=votes,
                    download_url=dl_url,
                    is_ogg=is_ogg,
                    forvo_id=forvo_id,
                ))

    # Sort by votes descending
    results.sort(key=lambda p: p.votes, reverse=True)
    return results


def download_pronunciation(pron: ForvoPronunciation, dest_dir: str) -> str:
    """
    Download a pronunciation file to dest_dir.

    Returns:
        The filename (not full path) of the saved file.
    """
    scraper = _get_scraper()

    ext = ".ogg" if pron.is_ogg else ".mp3"
    safe_word = pron.word.replace("/", "-").replace("\\", "-")
    for ch in '<>:"|?*':
        safe_word = safe_word.replace(ch, "_")

    filename = f"pronunciation_{pron.language}_{safe_word}{ext}"

    os.makedirs(dest_dir, exist_ok=True)
    dl_path = os.path.join(dest_dir, filename)

    response = scraper.get(pron.download_url, stream=True)
    response.raise_for_status()
    with open(dl_path, "wb") as f:
        for chunk in response.iter_content(chunk_size=8192):
            if chunk:
                f.write(chunk)

    return filename


# --- CLI test ---
if __name__ == "__main__":
    import sys
    word = sys.argv[1] if len(sys.argv) > 1 else "Haus"
    lang = sys.argv[2] if len(sys.argv) > 2 else "de"
    print(f"Searching Forvo for '{word}' in '{lang}'...")
    results = search_forvo(word, lang)
    for i, p in enumerate(results):
        print(f"  [{i}] {p.user} ({p.origin}) — {p.votes} votes — {'ogg' if p.is_ogg else 'mp3'}")
    if not results:
        print("  No results found.")
