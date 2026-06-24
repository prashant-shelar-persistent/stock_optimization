#!/usr/bin/env python3
"""
confluence_uploader.py
======================
Upload / sync the docs/ folder to a Confluence space.

Usage
-----
    # 1. Copy the example env file and fill in your credentials:
    cp .env.confluence.example .env.confluence

    # 2. Run a dry-run to preview what will be created/updated:
    python confluence_uploader.py --dry-run

    # 3. Upload everything:
    python confluence_uploader.py

    # 4. Upload a single file:
    python confluence_uploader.py --file 01-getting-started/overview.md

    # 5. Use a custom config file:
    python confluence_uploader.py --config my_config.yaml

Requirements
------------
    pip install requests markdown PyYAML python-dotenv

Environment variables (see .env.confluence.example):
    CONFLUENCE_URL               Base URL of your Confluence instance
    CONFLUENCE_SPACE_KEY         Target space key
    CONFLUENCE_PARENT_PAGE_TITLE Root parent page title
    CONFLUENCE_EMAIL             Your Atlassian account email (Cloud)
    CONFLUENCE_API_TOKEN         API token (Cloud) or leave empty for PAT
    CONFLUENCE_PAT               Personal Access Token (Server/DC)
    CONFLUENCE_DRY_RUN           "true" to preview without uploading
    CONFLUENCE_WORKERS           Concurrent upload threads (default 4)
    CONFLUENCE_UPDATE_EXISTING   "true" to update existing pages
    CONFLUENCE_PAGE_LABEL        Label added to every page (optional)
"""

from __future__ import annotations

import argparse
import logging
import os
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

# ── Third-party imports (installed via requirements) ─────────────────────────
try:
    import requests
    from requests.adapters import HTTPAdapter
    from urllib3.util.retry import Retry
except ImportError:
    sys.exit("ERROR: 'requests' is not installed. Run: pip install requests")

try:
    import markdown
except ImportError:
    sys.exit("ERROR: 'markdown' is not installed. Run: pip install markdown")

try:
    import yaml
except ImportError:
    sys.exit("ERROR: 'PyYAML' is not installed. Run: pip install PyYAML")

try:
    from dotenv import load_dotenv
except ImportError:
    sys.exit("ERROR: 'python-dotenv' is not installed. Run: pip install python-dotenv")

# ─────────────────────────────────────────────────────────────────────────────
# Logging
# ─────────────────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("confluence_uploader")

# ─────────────────────────────────────────────────────────────────────────────
# Data classes
# ─────────────────────────────────────────────────────────────────────────────

DOCS_DIR = Path(__file__).parent


@dataclass
class PageSpec:
    """Represents a single page to be uploaded."""

    title: str
    file_path: Path  # absolute path to the .md file
    parent_title: Optional[str] = None
    children: list["PageSpec"] = field(default_factory=list)


@dataclass
class UploadResult:
    """Result of a single page upload attempt."""

    title: str
    file_path: Path
    status: str  # "created" | "updated" | "skipped" | "error" | "dry_run"
    page_id: Optional[str] = None
    page_url: Optional[str] = None
    error: Optional[str] = None


# ─────────────────────────────────────────────────────────────────────────────
# Configuration
# ─────────────────────────────────────────────────────────────────────────────

class ConfluenceConfig:
    """Loads and validates configuration from environment variables."""

    def __init__(self) -> None:
        # Load .env.confluence if it exists
        env_file = DOCS_DIR / ".env.confluence"
        if env_file.exists():
            load_dotenv(env_file)
            log.info("Loaded credentials from %s", env_file)
        else:
            load_dotenv()  # fall back to .env in cwd

        self.base_url: str = os.environ.get("CONFLUENCE_URL", "").rstrip("/")
        self.space_key: str = os.environ.get("CONFLUENCE_SPACE_KEY", "")
        self.parent_page_title: str = os.environ.get(
            "CONFLUENCE_PARENT_PAGE_TITLE", "Portfolio Optimizer Documentation"
        )
        self.email: str = os.environ.get("CONFLUENCE_EMAIL", "")
        self.api_token: str = os.environ.get("CONFLUENCE_API_TOKEN", "")
        self.pat: str = os.environ.get("CONFLUENCE_PAT", "")
        self.dry_run: bool = os.environ.get("CONFLUENCE_DRY_RUN", "false").lower() == "true"
        self.workers: int = int(os.environ.get("CONFLUENCE_WORKERS", "4"))
        self.update_existing: bool = (
            os.environ.get("CONFLUENCE_UPDATE_EXISTING", "true").lower() == "true"
        )
        self.page_label: str = os.environ.get("CONFLUENCE_PAGE_LABEL", "")

    def validate(self) -> None:
        """Raise ValueError if required fields are missing."""
        errors: list[str] = []
        if not self.base_url:
            errors.append("CONFLUENCE_URL is not set")
        if not self.space_key:
            errors.append("CONFLUENCE_SPACE_KEY is not set")
        if not self.email and not self.pat:
            errors.append(
                "Authentication missing: set CONFLUENCE_EMAIL + CONFLUENCE_API_TOKEN "
                "(Cloud) or CONFLUENCE_PAT (Server/DC)"
            )
        if self.email and not self.api_token:
            errors.append(
                "CONFLUENCE_EMAIL is set but CONFLUENCE_API_TOKEN is missing"
            )
        if errors:
            raise ValueError(
                "Configuration errors:\n" + "\n".join(f"  • {e}" for e in errors)
            )

    @property
    def auth(self) -> tuple[str, str] | None:
        """Return (email, api_token) for Basic auth, or None when using PAT."""
        if self.email and self.api_token:
            return (self.email, self.api_token)
        return None

    @property
    def headers(self) -> dict[str, str]:
        h: dict[str, str] = {"Content-Type": "application/json", "Accept": "application/json"}
        if self.pat:
            h["Authorization"] = f"Bearer {self.pat}"
        return h


# ─────────────────────────────────────────────────────────────────────────────
# Confluence REST API client
# ─────────────────────────────────────────────────────────────────────────────

class ConfluenceClient:
    """Thin wrapper around the Confluence REST API v2 (with v1 fallback)."""

    def __init__(self, config: ConfluenceConfig) -> None:
        self.config = config
        self.session = self._build_session()
        # Cache: title → page_id
        self._page_id_cache: dict[str, str] = {}

    def _build_session(self) -> requests.Session:
        session = requests.Session()
        retry = Retry(
            total=5,
            backoff_factor=1.0,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["GET", "POST", "PUT"],
        )
        adapter = HTTPAdapter(max_retries=retry)
        session.mount("https://", adapter)
        session.mount("http://", adapter)
        if self.config.auth:
            session.auth = self.config.auth
        session.headers.update(self.config.headers)
        return session

    # ── Low-level helpers ────────────────────────────────────────────────────

    def _api(self, path: str) -> str:
        """Build a full REST API URL."""
        return f"{self.config.base_url}/rest/api{path}"

    def _get(self, path: str, params: dict | None = None) -> dict:
        url = self._api(path)
        resp = self.session.get(url, params=params, timeout=30)
        resp.raise_for_status()
        return resp.json()

    def _post(self, path: str, payload: dict) -> dict:
        url = self._api(path)
        resp = self.session.post(url, json=payload, timeout=60)
        resp.raise_for_status()
        return resp.json()

    def _put(self, path: str, payload: dict) -> dict:
        url = self._api(path)
        resp = self.session.put(url, json=payload, timeout=60)
        resp.raise_for_status()
        return resp.json()

    # ── Page operations ──────────────────────────────────────────────────────

    def get_page_by_title(self, title: str, space_key: str) -> Optional[dict]:
        """Return the page dict if found, else None."""
        if title in self._page_id_cache:
            page_id = self._page_id_cache[title]
            try:
                return self._get(f"/content/{page_id}", params={"expand": "version,body.storage"})
            except requests.HTTPError:
                pass

        try:
            result = self._get(
                "/content",
                params={
                    "title": title,
                    "spaceKey": space_key,
                    "expand": "version,body.storage",
                    "limit": 1,
                },
            )
            results = result.get("results", [])
            if results:
                page = results[0]
                self._page_id_cache[title] = page["id"]
                return page
        except requests.HTTPError as exc:
            log.warning("Could not look up page '%s': %s", title, exc)
        return None

    def create_page(
        self,
        space_key: str,
        title: str,
        body_html: str,
        parent_id: Optional[str] = None,
        label: str = "",
    ) -> dict:
        """Create a new Confluence page and return the API response."""
        payload: dict[str, Any] = {
            "type": "page",
            "title": title,
            "space": {"key": space_key},
            "body": {
                "storage": {
                    "value": body_html,
                    "representation": "storage",
                }
            },
        }
        if parent_id:
            payload["ancestors"] = [{"id": parent_id}]

        page = self._post("/content", payload)
        page_id = page["id"]
        self._page_id_cache[title] = page_id

        if label:
            self._add_label(page_id, label)

        return page

    def update_page(
        self,
        page_id: str,
        title: str,
        body_html: str,
        current_version: int,
        label: str = "",
    ) -> dict:
        """Update an existing Confluence page."""
        payload: dict[str, Any] = {
            "type": "page",
            "title": title,
            "version": {"number": current_version + 1},
            "body": {
                "storage": {
                    "value": body_html,
                    "representation": "storage",
                }
            },
        }
        page = self._put(f"/content/{page_id}", payload)

        if label:
            self._add_label(page_id, label)

        return page

    def _add_label(self, page_id: str, label: str) -> None:
        """Add a label to a page (best-effort, errors are logged not raised)."""
        try:
            self._post(
                f"/content/{page_id}/label",
                [{"prefix": "global", "name": label}],  # type: ignore[arg-type]
            )
        except Exception as exc:  # noqa: BLE001
            log.debug("Could not add label '%s' to page %s: %s", label, page_id, exc)

    def get_page_url(self, page: dict) -> str:
        """Extract the web UI URL from a page response dict."""
        links = page.get("_links", {})
        base = links.get("base", self.config.base_url)
        web_ui = links.get("webui", "")
        return f"{base}{web_ui}"

    def test_connection(self) -> bool:
        """Return True if the Confluence instance is reachable and credentials work."""
        try:
            result = self._get(
                "/space",
                params={"spaceKey": self.config.space_key, "limit": 1},
            )
            spaces = result.get("results", [])
            if not spaces:
                log.error(
                    "Space '%s' not found. Check CONFLUENCE_SPACE_KEY.",
                    self.config.space_key,
                )
                return False
            log.info(
                "✓ Connected to Confluence — space: %s (%s)",
                spaces[0].get("name", ""),
                self.config.space_key,
            )
            return True
        except requests.ConnectionError as exc:
            log.error("Cannot reach Confluence at %s: %s", self.config.base_url, exc)
            return False
        except requests.HTTPError as exc:
            log.error("Authentication failed (%s). Check your credentials.", exc)
            return False


# ─────────────────────────────────────────────────────────────────────────────
# Markdown → Confluence Storage Format conversion
# ─────────────────────────────────────────────────────────────────────────────

# Markdown extensions that improve rendering in Confluence
_MD_EXTENSIONS = [
    "markdown.extensions.tables",
    "markdown.extensions.fenced_code",
    "markdown.extensions.codehilite",
    "markdown.extensions.toc",
    "markdown.extensions.nl2br",
    "markdown.extensions.sane_lists",
    "markdown.extensions.attr_list",
]


def markdown_to_confluence_storage(md_text: str) -> str:
    """
    Convert Markdown text to Confluence Storage Format (XHTML-like).

    Steps:
    1. Convert Markdown → HTML via the `markdown` library.
    2. Post-process the HTML to use Confluence-specific macros where
       appropriate (code blocks → ac:structured-macro code, etc.).
    """
    # Convert Markdown → HTML
    html = markdown.markdown(
        md_text,
        extensions=_MD_EXTENSIONS,
        extension_configs={
            "codehilite": {"css_class": "highlight", "guess_lang": False},
        },
    )

    # Post-process: wrap <pre><code class="language-X"> in Confluence code macro
    html = _convert_code_blocks(html)

    # Post-process: convert Mermaid fenced blocks to Confluence diagram macro
    html = _convert_mermaid_blocks(html)

    # Post-process: strip local .md links (Confluence uses page titles)
    html = _fix_internal_links(html)

    return html


def _convert_code_blocks(html: str) -> str:
    """
    Replace code blocks with the Confluence code structured macro.

    Handles two patterns produced by the markdown library:
    1. codehilite: <div class="codehilite"><pre>...</pre></div>
    2. fenced_code: <pre><code class="language-X">...</code></pre>
    """
    # Pattern 1: codehilite wraps in <div class="codehilite"><pre>...</pre></div>
    pattern_codehilite = re.compile(
        r'<div class="codehilite"><pre[^>]*><span></span><code[^>]*>(.*?)</code></pre></div>',
        re.DOTALL,
    )

    def replacer_codehilite(m: re.Match) -> str:
        inner = re.sub(r'<[^>]+>', '', m.group(1))
        inner = (
            inner.replace("&amp;", "&")
            .replace("&lt;", "<")
            .replace("&gt;", ">")
            .replace("&quot;", '"')
            .replace("&#39;", "'")
        )
        return (
            '<ac:structured-macro ac:name="code">'
            '<ac:parameter ac:name="language">none</ac:parameter>'
            f'<ac:plain-text-body><![CDATA[{inner}]]></ac:plain-text-body>'
            "</ac:structured-macro>"
        )

    html = pattern_codehilite.sub(replacer_codehilite, html)

    # Pattern 2: plain fenced code <pre><code class="language-X">...</code></pre>
    pattern_fenced = re.compile(
        r'<pre[^>]*><code(?:\s+class="(?:highlight\s+)?language-([^"]+)")?>(.*?)</code></pre>',
        re.DOTALL,
    )

    def replacer_fenced(m: re.Match) -> str:
        lang = m.group(1) or "none"
        code = m.group(2)
        code = (
            code.replace("&amp;", "&")
            .replace("&lt;", "<")
            .replace("&gt;", ">")
            .replace("&quot;", '"')
            .replace("&#39;", "'")
        )
        return (
            '<ac:structured-macro ac:name="code">'
            f'<ac:parameter ac:name="language">{lang}</ac:parameter>'
            f'<ac:plain-text-body><![CDATA[{code}]]></ac:plain-text-body>'
            "</ac:structured-macro>"
        )

    return pattern_fenced.sub(replacer_fenced, html)


def _convert_mermaid_blocks(html: str) -> str:
    """
    Replace <pre><code class="language-mermaid">…</code></pre> (already
    converted by _convert_code_blocks) with a Confluence ``noformat`` macro
    so the diagram source is at least readable.

    If your Confluence instance has the Mermaid plugin installed, you can
    change this to use the ``mermaid`` macro instead.
    """
    pattern = re.compile(
        r'<ac:structured-macro ac:name="code">'
        r'<ac:parameter ac:name="language">mermaid</ac:parameter>'
        r'<ac:plain-text-body><!\[CDATA\[(.*?)\]\]></ac:plain-text-body>'
        r"</ac:structured-macro>",
        re.DOTALL,
    )

    def replacer(m: re.Match) -> str:
        source = m.group(1).strip()
        return (
            '<ac:structured-macro ac:name="noformat">'
            f'<ac:plain-text-body><![CDATA[{source}]]></ac:plain-text-body>'
            "</ac:structured-macro>"
        )

    return pattern.sub(replacer, html)


def _fix_internal_links(html: str) -> str:
    """
    Remove or neutralise relative .md links so they don't break in Confluence.
    e.g. href="overview.md" → href="#" (Confluence cross-page links require
    the ac:link macro which needs page IDs — left as a future enhancement).
    """
    return re.sub(r'href="([^"]*\.md[^"]*)"', r'href="#"', html)


# ─────────────���─���─────────────────────────────────────────────────────────────
# Page hierarchy builder
# ─────────────────────────────────────────────────────────────────────────────

def load_page_specs(config_path: Path, docs_dir: Path) -> list[PageSpec]:
    """
    Parse confluence_config.yaml and return a flat list of PageSpec objects
    with parent_title set correctly for each page.
    """
    with config_path.open() as fh:
        raw = yaml.safe_load(fh)

    root_title: str = raw.get("root_title", "Portfolio Optimizer Documentation")
    pages_raw: list[dict] = raw.get("pages", [])

    specs: list[PageSpec] = []

    def _recurse(entries: list[dict], parent: str) -> None:
        for entry in entries:
            title = entry["title"]
            rel_file = entry.get("file", "")
            abs_file = (docs_dir / rel_file).resolve() if rel_file else None

            if abs_file and not abs_file.exists():
                log.warning("File not found, skipping: %s", abs_file)
                continue

            spec = PageSpec(
                title=title,
                file_path=abs_file or Path("/dev/null"),
                parent_title=parent,
            )
            specs.append(spec)

            children = entry.get("children", [])
            if children:
                _recurse(children, title)

    _recurse(pages_raw, root_title)
    return specs


def discover_all_docs(docs_dir: Path, root_title: str) -> list[PageSpec]:
    """
    Auto-discover all .md files in docs_dir and build a flat page list.
    Used as a fallback when no confluence_config.yaml is present.
    """
    specs: list[PageSpec] = []
    for md_file in sorted(docs_dir.rglob("*.md")):
        # Skip hidden files
        if any(part.startswith(".") for part in md_file.parts):
            continue
        # Build a human-readable title from the filename
        title = md_file.stem.replace("-", " ").replace("_", " ").title()
        # Use the parent directory name as a prefix for uniqueness
        parent_dir = md_file.parent.name
        if parent_dir != docs_dir.name:
            title = f"{parent_dir.lstrip('0123456789-').replace('-', ' ').title()} — {title}"
        specs.append(PageSpec(title=title, file_path=md_file, parent_title=root_title))
    return specs


# ─────────────────────────────────────────────────────────────────────────────
# Upload logic
# ─────────────────────────────────────────────────────────────────────────────

class ConfluenceUploader:
    """Orchestrates the upload of all pages."""

    def __init__(self, config: ConfluenceConfig, client: ConfluenceClient) -> None:
        self.config = config
        self.client = client
        # title → page_id for pages we've already created this run
        self._created_ids: dict[str, str] = {}

    def _get_parent_id(self, parent_title: str) -> Optional[str]:
        """Resolve a parent page title to its Confluence page ID."""
        # Check pages created in this run first
        if parent_title in self._created_ids:
            return self._created_ids[parent_title]
        # Fall back to API lookup
        page = self.client.get_page_by_title(parent_title, self.config.space_key)
        if page:
            return page["id"]
        log.warning("Parent page '%s' not found — page will be created at space root.", parent_title)
        return None

    def upload_page(self, spec: PageSpec) -> UploadResult:
        """Upload (create or update) a single page. Thread-safe."""
        title = spec.title
        file_path = spec.file_path

        # Read and convert the Markdown source
        try:
            md_text = file_path.read_text(encoding="utf-8")
        except OSError as exc:
            return UploadResult(title=title, file_path=file_path, status="error", error=str(exc))

        body_html = markdown_to_confluence_storage(md_text)

        if self.config.dry_run:
            log.info("[DRY-RUN] Would upload: '%s' ← %s", title, file_path.name)
            return UploadResult(title=title, file_path=file_path, status="dry_run")

        # Resolve parent
        parent_id = self._get_parent_id(spec.parent_title) if spec.parent_title else None

        # Check if page already exists
        existing = self.client.get_page_by_title(title, self.config.space_key)

        try:
            if existing:
                if not self.config.update_existing:
                    log.info("  SKIP  '%s' (already exists, update disabled)", title)
                    return UploadResult(
                        title=title,
                        file_path=file_path,
                        status="skipped",
                        page_id=existing["id"],
                        page_url=self.client.get_page_url(existing),
                    )
                current_version = existing["version"]["number"]
                page = self.client.update_page(
                    page_id=existing["id"],
                    title=title,
                    body_html=body_html,
                    current_version=current_version,
                    label=self.config.page_label,
                )
                url = self.client.get_page_url(page)
                log.info("  UPDATE '%s' → %s", title, url)
                return UploadResult(
                    title=title,
                    file_path=file_path,
                    status="updated",
                    page_id=page["id"],
                    page_url=url,
                )
            else:
                page = self.client.create_page(
                    space_key=self.config.space_key,
                    title=title,
                    body_html=body_html,
                    parent_id=parent_id,
                    label=self.config.page_label,
                )
                page_id = page["id"]
                self._created_ids[title] = page_id
                url = self.client.get_page_url(page)
                log.info("  CREATE '%s' → %s", title, url)
                return UploadResult(
                    title=title,
                    file_path=file_path,
                    status="created",
                    page_id=page_id,
                    page_url=url,
                )
        except requests.HTTPError as exc:
            error_msg = f"HTTP {exc.response.status_code}: {exc.response.text[:200]}"
            log.error("  ERROR  '%s': %s", title, error_msg)
            return UploadResult(title=title, file_path=file_path, status="error", error=error_msg)
        except Exception as exc:  # noqa: BLE001
            log.error("  ERROR  '%s': %s", title, exc)
            return UploadResult(title=title, file_path=file_path, status="error", error=str(exc))

    def upload_all(self, specs: list[PageSpec]) -> list[UploadResult]:
        """
        Upload all pages.

        Pages are uploaded sequentially in the order they appear in `specs`
        to ensure parent pages exist before their children. Within a batch
        of sibling pages, uploads are parallelised up to `config.workers`.
        """
        results: list[UploadResult] = []

        # Group specs by depth (parent_title == None → depth 0, etc.)
        # Since specs are already in BFS order from load_page_specs, we
        # process them in order but use a thread pool for I/O-bound HTTP calls.
        log.info("Starting upload of %d pages (workers=%d) …", len(specs), self.config.workers)

        # We upload in order to respect parent→child dependency, but use a
        # small thread pool to parallelise sibling pages.
        # Strategy: group consecutive specs that share the same parent_title.
        groups: list[list[PageSpec]] = []
        current_group: list[PageSpec] = []
        current_parent: Optional[str] = None

        for spec in specs:
            if spec.parent_title != current_parent:
                if current_group:
                    groups.append(current_group)
                current_group = [spec]
                current_parent = spec.parent_title
            else:
                current_group.append(spec)
        if current_group:
            groups.append(current_group)

        for group in groups:
            if len(group) == 1:
                results.append(self.upload_page(group[0]))
            else:
                with ThreadPoolExecutor(max_workers=min(self.config.workers, len(group))) as pool:
                    futures = {pool.submit(self.upload_page, spec): spec for spec in group}
                    for future in as_completed(futures):
                        results.append(future.result())
            # Brief pause between groups to avoid rate-limiting
            time.sleep(0.2)

        return results


# ─────────────────────────────────────────────────────────────────────────────
# Summary report
# ─────────────────────────────────────────────────────────────────────────────

def print_summary(results: list[UploadResult], dry_run: bool) -> None:
    """Print a coloured summary table to stdout."""
    counts: dict[str, int] = {"created": 0, "updated": 0, "skipped": 0, "error": 0, "dry_run": 0}
    for r in results:
        counts[r.status] = counts.get(r.status, 0) + 1

    print("\n" + "─" * 70)
    if dry_run:
        print(f"  DRY-RUN SUMMARY — {len(results)} pages would be processed")
    else:
        print(f"  UPLOAD SUMMARY — {len(results)} pages processed")
    print("─" * 70)
    print(f"  ✅  Created : {counts['created']}")
    print(f"  🔄  Updated : {counts['updated']}")
    print(f"  ⏭   Skipped : {counts['skipped']}")
    print(f"  🔍  Dry-run : {counts['dry_run']}")
    print(f"  ❌  Errors  : {counts['error']}")
    print("─" * 70)

    if counts["error"]:
        print("\nFailed pages:")
        for r in results:
            if r.status == "error":
                print(f"  • {r.title}: {r.error}")
        print()

    if not dry_run and (counts["created"] + counts["updated"]) > 0:
        print("\nSuccessfully uploaded pages:")
        for r in results:
            if r.status in ("created", "updated"):
                action = "CREATED" if r.status == "created" else "UPDATED"
                print(f"  [{action}] {r.title}")
                if r.page_url:
                    print(f"           {r.page_url}")
        print()


# ─────────────────────────────────────────────────────────────────────────────
# CLI entry point
# ─────────────────────────────────────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Upload docs/ folder to Confluence",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--config",
        default=str(DOCS_DIR / "confluence_config.yaml"),
        help="Path to the YAML page hierarchy config (default: docs/confluence_config.yaml)",
    )
    parser.add_argument(
        "--file",
        metavar="RELATIVE_PATH",
        help="Upload only this single file (relative to docs/)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview what would be uploaded without making any changes",
    )
    parser.add_argument(
        "--no-update",
        action="store_true",
        help="Skip pages that already exist (do not update them)",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=None,
        help="Number of concurrent upload threads (overrides CONFLUENCE_WORKERS)",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable DEBUG logging",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # ── Load & validate config ────────────────────────────────────────────────
    config = ConfluenceConfig()

    # CLI flags override env vars
    if args.dry_run:
        config.dry_run = True
    if args.no_update:
        config.update_existing = False
    if args.workers is not None:
        config.workers = args.workers

    if config.dry_run:
        log.info("DRY-RUN mode enabled — no pages will be created or updated.")

    try:
        config.validate()
    except ValueError as exc:
        log.error("%s", exc)
        log.error(
            "\nCopy docs/.env.confluence.example to docs/.env.confluence "
            "and fill in your Confluence credentials."
        )
        return 1

    # ── Build Confluence client ───────────────────────────────────────────────
    client = ConfluenceClient(config)

    if not config.dry_run:
        if not client.test_connection():
            return 1

    # ── Build page spec list ──────────────────────────────────────────────────
    config_path = Path(args.config)

    if args.file:
        # Single-file mode
        target = (DOCS_DIR / args.file).resolve()
        if not target.exists():
            log.error("File not found: %s", target)
            return 1
        title = target.stem.replace("-", " ").replace("_", " ").title()
        specs = [PageSpec(title=title, file_path=target, parent_title=config.parent_page_title)]
        log.info("Single-file mode: uploading '%s'", target.name)
    elif config_path.exists():
        log.info("Loading page hierarchy from %s", config_path)
        specs = load_page_specs(config_path, DOCS_DIR)
        log.info("Found %d pages in config", len(specs))
    else:
        log.info("No config file found — auto-discovering all .md files in docs/")
        specs = discover_all_docs(DOCS_DIR, config.parent_page_title)
        log.info("Discovered %d markdown files", len(specs))

    if not specs:
        log.warning("No pages to upload.")
        return 0

    # ── Upload ────────────────────────────────────────────────────────────────
    uploader = ConfluenceUploader(config, client)
    results = uploader.upload_all(specs)

    # ── Summary ───────────────────────────────────────────────────────────────
    print_summary(results, config.dry_run)

    error_count = sum(1 for r in results if r.status == "error")
    return 1 if error_count > 0 else 0


if __name__ == "__main__":
    sys.exit(main())
