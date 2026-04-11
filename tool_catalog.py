from __future__ import annotations

"""Isaac – Local Tool Catalog
Vordefinierte lokale Tool-Schnittstellen, die ohne schweren Zusatz-Stack
im Dashboard angeboten und in die Registry installiert werden können.
"""

from copy import deepcopy
from typing import Any

LOCAL_TOOL_CATALOG: list[dict[str, Any]] = [
    {
        "catalog_id": "local_search_duckduckgo",
        "name": "DuckDuckGo Instant Search",
        "kind": "search",
        "category": "suche",
        "description": "Leichtgewichtige Websuche über die DuckDuckGo-Instant-Answer-Schnittstelle.",
        "base_url": "https://api.duckduckgo.com/",
        "query_param": "q",
        "method": "GET",
        "size_mb": 0.0,
        "install_mode": "register_only",
        "active": True,
        "priority": 72,
        "trust": 58.0,
        "metadata": {"return_format": "json", "source": "catalog", "local": True},
    },
    {
        "catalog_id": "local_http_json_adapter",
        "name": "HTTP JSON Adapter",
        "kind": "api",
        "category": "general",
        "description": "Generischer lokaler HTTP/JSON-Adapter für REST-Tools.",
        "base_url": "http://127.0.0.1:8080/api/tool",
        "endpoint": "",
        "query_param": "q",
        "method": "POST",
        "size_mb": 0.1,
        "install_mode": "register_only",
        "active": False,
        "priority": 60,
        "trust": 50.0,
        "metadata": {"source": "catalog", "local": True},
    },
    {
        "catalog_id": "local_script_runner",
        "name": "Local Script Runner",
        "kind": "script",
        "category": "code",
        "description": "Bindet lokale Skripte als Isaac-Tool ein. Geeignet für kleine Helfer in Termux/Alpine.",
        "script_path": "./tools/example_tool.sh",
        "method": "EXEC",
        "size_mb": 0.0,
        "install_mode": "register_only",
        "active": False,
        "priority": 64,
        "trust": 52.0,
        "metadata": {"source": "catalog", "local": True, "requires_path_edit": True},
    },
    {
        "catalog_id": "local_browser_chat_bridge",
        "name": "Browser Chat Bridge",
        "kind": "browser_chat",
        "category": "suche",
        "description": "Bridge für browsergestützte Chat-/Recherche-Instanzen.",
        "website_url": "https://example.local/browser-chat",
        "method": "BROWSER",
        "size_mb": 0.4,
        "install_mode": "register_only",
        "active": False,
        "priority": 68,
        "trust": 50.0,
        "metadata": {"source": "catalog", "local": True},
    },
    {
        "catalog_id": "local_mcp_bridge",
        "name": "MCP Bridge",
        "kind": "mcp",
        "category": "integration",
        "description": "MCP-nahe Bridge für Tools, Resources und Prompts über eine lokale HTTP-Bridge.",
        "base_url": "http://127.0.0.1:8766/api/mcp",
        "method": "POST",
        "size_mb": 0.2,
        "install_mode": "register_only",
        "active": False,
        "priority": 70,
        "trust": 54.0,
        "metadata": {"source": "catalog", "local": True, "mcp_like": True, "features": ["tools", "resources", "prompts"]},
    },
    {
        "catalog_id": "public_wikipedia_opensearch",
        "name": "Wikipedia Opensearch",
        "kind": "search",
        "category": "suche",
        "description": "Offizielle Wikipedia-Titelsuche ueber MediaWiki Opensearch.",
        "base_url": "https://en.wikipedia.org/w/api.php?action=opensearch&format=json&limit=5&namespace=0",
        "query_param": "search",
        "method": "GET",
        "size_mb": 0.0,
        "install_mode": "register_only",
        "active": True,
        "priority": 74,
        "trust": 60.0,
        "metadata": {
            "return_format": "json",
            "source": "catalog",
            "local": True,
            "starter_pack": "free",
            "docs_url": "https://www.mediawiki.org/wiki/API:Opensearch",
        },
    },
    {
        "catalog_id": "public_openlibrary_search",
        "name": "Open Library Search",
        "kind": "search",
        "category": "research",
        "description": "Offizielle Open-Library-Buchsuche fuer frei verfuegbare Buch- und Werkinfos.",
        "base_url": "https://openlibrary.org/search.json?limit=5",
        "query_param": "q",
        "method": "GET",
        "size_mb": 0.0,
        "install_mode": "register_only",
        "active": True,
        "priority": 73,
        "trust": 60.0,
        "metadata": {
            "return_format": "json",
            "source": "catalog",
            "local": True,
            "starter_pack": "free",
            "docs_url": "https://openlibrary.org/dev/docs/api/search",
        },
    },
    {
        "catalog_id": "public_stackoverflow_search",
        "name": "Stack Overflow Search",
        "kind": "search",
        "category": "code",
        "description": "Offizielle Stack-Exchange-Suche fuer technische Fragen auf Stack Overflow.",
        "base_url": "https://api.stackexchange.com/2.3/search?order=desc&sort=relevance&site=stackoverflow",
        "query_param": "intitle",
        "method": "GET",
        "size_mb": 0.0,
        "install_mode": "register_only",
        "active": True,
        "priority": 78,
        "trust": 63.0,
        "metadata": {
            "return_format": "json",
            "source": "catalog",
            "local": True,
            "starter_pack": "free",
            "docs_url": "https://api.stackexchange.com/docs/search",
        },
    },
    {
        "catalog_id": "public_openmeteo_geocoding",
        "name": "Open-Meteo Geocoding",
        "kind": "search",
        "category": "wetter",
        "description": "Offizielle Gratis-Geocoding-Suche von Open-Meteo fuer Wetter-Ortsaufloesung.",
        "base_url": "https://geocoding-api.open-meteo.com/v1/search?count=5&language=de&format=json",
        "query_param": "name",
        "method": "GET",
        "size_mb": 0.0,
        "install_mode": "register_only",
        "active": True,
        "priority": 76,
        "trust": 64.0,
        "metadata": {
            "return_format": "json",
            "source": "catalog",
            "local": True,
            "starter_pack": "free",
            "docs_url": "https://open-meteo.com/en/docs/geocoding-api",
        },
    },
    {
        "catalog_id": "public_crossref_works",
        "name": "Crossref Works Search",
        "kind": "search",
        "category": "research",
        "description": "Offizielle Crossref-Metadatensuche fuer Paper, DOIs und Publikationen.",
        "base_url": "https://api.crossref.org/works?rows=5&select=DOI,title,author,published,URL",
        "query_param": "query.bibliographic",
        "method": "GET",
        "size_mb": 0.0,
        "install_mode": "register_only",
        "active": True,
        "priority": 74,
        "trust": 62.0,
        "metadata": {
            "return_format": "json",
            "source": "catalog",
            "local": True,
            "starter_pack": "free",
            "docs_url": "https://www.crossref.org/documentation/retrieve-metadata/rest-api/",
        },
    },
    {
        "catalog_id": "public_pubmed_search",
        "name": "PubMed Search",
        "kind": "search",
        "category": "research",
        "description": "Offizielle NCBI PubMed-Suche über E-utilities.",
        "base_url": "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi?db=pubmed&retmode=json&retmax=5&sort=relevance",
        "query_param": "term",
        "method": "GET",
        "size_mb": 0.0,
        "install_mode": "register_only",
        "active": True,
        "priority": 75,
        "trust": 63.0,
        "metadata": {
            "return_format": "json",
            "source": "catalog",
            "local": True,
            "starter_pack": "free",
            "docs_url": "https://www.ncbi.nlm.nih.gov/books/NBK25499/",
        },
    },
    {
        "catalog_id": "public_github_repo_search",
        "name": "GitHub Repository Search",
        "kind": "search",
        "category": "code",
        "description": "Offizielle GitHub-Repositoriesuche über die öffentliche REST-Schnittstelle.",
        "base_url": "https://api.github.com/search/repositories?per_page=5&sort=stars&order=desc",
        "query_param": "q",
        "method": "GET",
        "size_mb": 0.0,
        "install_mode": "register_only",
        "active": True,
        "priority": 76,
        "trust": 62.0,
        "metadata": {
            "return_format": "json",
            "source": "catalog",
            "local": True,
            "starter_pack": "free",
            "docs_url": "https://docs.github.com/en/rest/search/search#search-repositories",
        },
    },
    {
        "catalog_id": "public_github_issue_search",
        "name": "GitHub Issue Search",
        "kind": "search",
        "category": "code",
        "description": "Offizielle GitHub-Issue- und PR-Suche über die öffentliche REST-Schnittstelle.",
        "base_url": "https://api.github.com/search/issues?per_page=5&sort=updated&order=desc",
        "query_param": "q",
        "method": "GET",
        "size_mb": 0.0,
        "install_mode": "register_only",
        "active": True,
        "priority": 75,
        "trust": 61.0,
        "metadata": {
            "return_format": "json",
            "source": "catalog",
            "local": True,
            "starter_pack": "free",
            "docs_url": "https://docs.github.com/en/rest/search/search#search-issues-and-pull-requests",
        },
    },
]

TOOL_BUNDLES: dict[str, dict[str, Any]] = {
    "free_starter_pack": {
        "bundle_id": "free_starter_pack",
        "label": "Free Starter Pack",
        "description": "Schneller Einstieg mit allgemeinen Gratis-Webtools fuer Suche, Wetter und Code.",
        "catalog_ids": [
            "local_search_duckduckgo",
            "public_wikipedia_opensearch",
            "public_stackoverflow_search",
            "public_openmeteo_geocoding",
        ],
    },
    "free_research_pack": {
        "bundle_id": "free_research_pack",
        "label": "Free Research Pack",
        "description": "Freie Recherche-Quellen fuer Paper, Buecher, Wissen und medizinische Literatur.",
        "catalog_ids": [
            "public_wikipedia_opensearch",
            "public_openlibrary_search",
            "public_crossref_works",
            "public_pubmed_search",
            "public_openmeteo_geocoding",
        ],
    },
    "free_dev_pack": {
        "bundle_id": "free_dev_pack",
        "label": "Free Dev Pack",
        "description": "Freie Entwicklerquellen fuer Codefragen, Repositories, Issues und Websuche.",
        "catalog_ids": [
            "local_search_duckduckgo",
            "public_stackoverflow_search",
            "public_github_repo_search",
            "public_github_issue_search",
        ],
    },
}


def list_local_tool_catalog() -> list[dict[str, Any]]:
    return [deepcopy(item) for item in LOCAL_TOOL_CATALOG]


def get_catalog_item(catalog_id: str) -> dict[str, Any] | None:
    for item in LOCAL_TOOL_CATALOG:
        if item["catalog_id"] == catalog_id:
            return deepcopy(item)
    return None


def free_starter_pack_catalog_ids() -> list[str]:
    return list(TOOL_BUNDLES["free_starter_pack"]["catalog_ids"])


def list_tool_bundles() -> list[dict[str, Any]]:
    return [deepcopy(item) for item in TOOL_BUNDLES.values()]


def bundle_catalog_ids(bundle_id: str) -> list[str]:
    bundle = TOOL_BUNDLES.get(bundle_id)
    if not bundle:
        raise KeyError(f"Unbekanntes Tool-Bundle: {bundle_id}")
    return list(bundle.get("catalog_ids") or [])


def registry_payload_from_catalog(catalog_id: str) -> dict[str, Any]:
    item = get_catalog_item(catalog_id)
    if not item:
        raise KeyError(f"Unbekannter Katalogeintrag: {catalog_id}")
    payload = deepcopy(item)
    payload.pop("catalog_id", None)
    payload.pop("size_mb", None)
    payload.pop("install_mode", None)
    meta = dict(payload.get("metadata") or {})
    meta["catalog_id"] = catalog_id
    payload["metadata"] = meta
    return payload
