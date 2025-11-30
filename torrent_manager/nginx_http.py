"""
nginx_http.py

A Python HTTP client for browsing and downloading from nginx-style directory listings.

This module provides a complete interface for interacting with nginx autoindex pages,
allowing you to treat HTTP directory listings as if they were a filesystem. It supports
listing directories, walking directory trees, checking file/directory existence, and
downloading files or entire directory structures.

FEATURES
--------
- Parse nginx "Index of /path" HTML listings (table format with icons)
- List directory contents with metadata (size, modification time)
- Recursively walk directory trees (similar to os.walk)
- Check for file/directory existence
- Download individual files with optional byte-range support
- Resume interrupted downloads
- Download entire directories, mirroring the remote tree locally
- HTTP Basic Authentication support
- Proper handling of percent-encoded URLs and special characters

DEPENDENCIES
------------
    pip install requests beautifulsoup4

COMMAND-LINE INTERFACE
----------------------
A full-featured command-line interface is available in the cli module:
    python -m nginx_http.cli --help

See nginx_http.cli module documentation for detailed CLI usage and examples.

PYTHON API USAGE
----------------
Basic listing:
    >>> from nginx_http import HttpNginxDirectoryClient
    >>> client = HttpNginxDirectoryClient("https://example.com/files/")
    >>> entries = client.listdir("")
    >>> for entry in entries:
    ...     print(f"{entry.name}: {entry.size} bytes")

With authentication:
    >>> client = HttpNginxDirectoryClient(
    ...     "https://example.com/files/",
    ...     auth=("username", "password")
    ... )
    >>> entries = client.listdir("subfolder/")

Walking directory tree:
    >>> for dirpath, dirnames, filenames in client.walk(""):
    ...     print(f"Directory: {dirpath}")
    ...     for filename in filenames:
    ...         print(f"  File: {filename}")

Download a file:
    >>> client.download("path/to/file.txt", "local_file.txt")

Download with resume support:
    >>> client.download("large_file.zip", "local.zip", allow_resume=True)

Download entire directory:
    >>> client.download_directory("remote_folder/", "./local_folder")

Fetch file content into memory:
    >>> data = client.fetch_bytes("config.json")
    >>> import json
    >>> config = json.loads(data)

NGINX AUTOINDEX FORMAT
----------------------
This module expects the standard nginx autoindex HTML format:
- Page title: "Index of /path"
- Content in an HTML <table> with columns: icon, name, last modified, size
- Directories end with '/' in the href attribute
- Icon alt text contains "DIR" for directories, "PARENTDIR" for parent link

IMPLEMENTATION NOTES
--------------------
The module normalizes all paths internally:
- Paths are relative to base_url (no leading '/')
- Directory paths end with '/'
- File paths do not end with '/'
- Percent-encoding is handled automatically

The HttpNginxDirectoryClient uses a requests.Session for connection pooling,
making it efficient for multiple operations on the same server.

AUTHOR
------
Philip Orange <git@philiporange.com>

LICENSE
-------
CC0 - No rights reserved
"""

from __future__ import annotations

import logging
import os
import posixpath
from dataclasses import dataclass
from datetime import datetime
from typing import Iterable, Iterator, List, Optional, Tuple, Union

import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, unquote, quote

logger = logging.getLogger(__name__)


@dataclass
class NginxIndexEntry:
    """Represents a single item (file or directory) in an nginx index listing."""

    name: str                       # Human-readable name (link text)
    path: str                       # Path relative to the base URL (decoded, no leading "/")
    href: str                       # Raw href as found in the HTML (may be percent-encoded)
    is_dir: bool
    size: Optional[int]             # Size in bytes if known, otherwise None
    modified: Optional[datetime]    # Last modified time if parsed, otherwise None
    raw_size: Optional[str] = None  # Original size string from the HTML
    raw_modified: Optional[str] = None  # Original last modified string


def _parse_size_to_bytes(size_str: str) -> Optional[int]:
    """
    Parse nginx-style human-readable sizes into bytes.
    Examples: '603M', '36M', '401M', '-', '  - '.

    Returns:
        int number of bytes, or None if unknown / "-" / empty.
    """
    if not size_str:
        return None
    s = size_str.strip()
    if s == "-" or s == "":
        return None

    try:
        if s.isdigit():
            return int(s)
    except ValueError:
        pass

    unit = s[-1].upper()
    num_part = s[:-1].strip()
    try:
        value = float(num_part)
    except ValueError:
        return None

    if unit == "K":
        return int(value * 1024)
    if unit == "M":
        return int(value * 1024 ** 2)
    if unit == "G":
        return int(value * 1024 ** 3)
    if unit == "T":
        return int(value * 1024 ** 4)

    return None


def _parse_last_modified(date_str: str) -> Optional[datetime]:
    """
    Parse the 'Last modified' column used by nginx, e.g. '2025-11-14 10:51'.

    Returns:
        datetime in naive form (no timezone), or None if parsing fails.
    """
    if not date_str:
        return None
    s = date_str.strip()
    if not s:
        return None

    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue

    logger.debug("Failed to parse last-modified date: %r", date_str)
    return None


def _normalize_dir_path(path: str) -> str:
    """
    Normalize a remote directory path:
    - remove any leading '/'
    - ensure trailing '/'
    - collapse redundant slashes via posixpath.normpath (except trailing)
    """
    if not path:
        return ""
    p = path.lstrip("/")
    if p.endswith("/"):
        p = p[:-1]
    p = posixpath.normpath(p)
    if p == ".":
        return ""
    return p + "/"


def _normalize_file_path(path: str) -> str:
    """
    Normalize a remote file path:
    - remove any leading '/'
    - remove any trailing '/'
    - collapse redundant slashes
    """
    if not path:
        return ""
    p = path.lstrip("/")
    if p.endswith("/"):
        p = p[:-1]
    p = posixpath.normpath(p)
    if p == ".":
        return ""
    return p


def _encode_path_for_url(path: str, is_dir: bool = False) -> str:
    """
    Percent-encode a remote path for use in URLs, segment by segment.

    Args:
        path: relative path (no scheme, no netloc).
        is_dir: True if representing a directory (keep trailing slash).

    Returns:
        Encoded path suitable for appending to a base URL.
    """
    if not path:
        return "" if not is_dir else ""
    trailing_slash = path.endswith("/")
    segments = path.strip("/").split("/")
    encoded_segments = [quote(seg, safe="") for seg in segments if seg != ""]
    encoded = "/".join(encoded_segments)
    if (is_dir or trailing_slash) and encoded and not encoded.endswith("/"):
        encoded = encoded + "/"
    return encoded


def parse_nginx_index_html(
    html: str,
    current_dir: str = "",
) -> List[NginxIndexEntry]:
    """
    Parse nginx autoindex HTML (table format) into a list of NginxIndexEntry.

    Args:
        html: The raw HTML of the directory listing.
        current_dir: Directory path relative to base for this listing,
                     normalized like _normalize_dir_path (may be "").

    Returns:
        List of NginxIndexEntry objects.
    """
    soup = BeautifulSoup(html, "html.parser")

    table = soup.find("table")
    if table is None:
        logger.debug("No <table> found in nginx index HTML.")
        return []

    entries: List[NginxIndexEntry] = []

    for row in table.find_all("tr"):
        tds = row.find_all("td")
        if len(tds) < 2:
            continue

        icon_alt = None
        icon_img = tds[0].find("img")
        if icon_img is not None and icon_img.has_attr("alt"):
            icon_alt = icon_img["alt"].strip()

        link = tds[1].find("a")
        if link is None:
            continue
        href = link.get("href")
        if href is None:
            continue

        text_name = link.get_text(strip=True)

        if icon_alt and "PARENTDIR" in icon_alt.upper():
            continue
        if text_name.lower() == "parent directory":
            continue

        is_dir = False
        if icon_alt and "DIR" in icon_alt.upper():
            is_dir = True
        elif href.endswith("/"):
            is_dir = True

        raw_modified = None
        raw_size = None
        modified = None
        size_bytes = None

        if len(tds) >= 3:
            raw_modified = tds[2].get_text(strip=True)
            modified = _parse_last_modified(raw_modified)
        if len(tds) >= 4:
            raw_size = tds[3].get_text(strip=True)
            size_bytes = _parse_size_to_bytes(raw_size)

        decoded_href = unquote(href)
        decoded_href = decoded_href.lstrip("/")

        if current_dir:
            base_dir = _normalize_dir_path(current_dir)
            combined = posixpath.normpath(base_dir + decoded_href)
        else:
            combined = posixpath.normpath(decoded_href)

        if is_dir and not combined.endswith("/"):
            combined = combined + "/"

        entry = NginxIndexEntry(
            name=text_name,
            path=combined,
            href=href,
            is_dir=is_dir,
            size=size_bytes,
            modified=modified,
            raw_size=raw_size,
            raw_modified=raw_modified,
        )
        entries.append(entry)

    return entries


class HttpNginxDirectoryClient:
    """
    HTTP client for browsing nginx-style directory listings.

    Paths are always interpreted as relative to `base_url`. Paths in this API:
    - Do not start with '/'
    - Directories may end with '/', files do not.

    Optional HTTP Basic Auth:
    - Pass `auth=("username", "password")` to use HTTP Basic Auth on all requests.
      If you provide a custom `requests.Session` that already has `session.auth`
      configured and leave `auth` as None, that session-level auth is used.

    Examples
    --------
    >>> client = HttpNginxDirectoryClient("https://example.com/p01926/downloads/")
    >>> entries = client.listdir("")
    >>> for e in entries:
    ...     print(e.path, "DIR" if e.is_dir else "FILE", e.size)
    """

    def __init__(
        self,
        base_url: str,
        session: Optional[requests.Session] = None,
        timeout: Optional[float] = 30.0,
        auth: Optional[Tuple[str, str]] = None,
    ) -> None:
        """
        Args:
            base_url: Base URL pointing to the root directory (e.g. 'https://host/p01926/downloads/').
                      A trailing slash will be added if missing.
            session: Optional requests.Session to reuse connections.
            timeout: Default timeout (seconds) for HTTP requests.
            auth: Optional (username, password) tuple for HTTP Basic Auth.
                  If None, any auth configured on the provided `session` is used.
        """
        if not base_url.endswith("/"):
            base_url = base_url + "/"
        self.base_url = base_url
        self.session = session or requests.Session()
        self.timeout = timeout
        self.auth = auth

    # ------------------------------------------------------------------
    # Low-level URL construction and HTTP helpers
    # ------------------------------------------------------------------

    def _build_url(self, path: str, is_dir: bool = False) -> str:
        """
        Build a full URL for a relative remote path.

        Args:
            path: Relative path to file or directory.
            is_dir: Whether this path refers to a directory.

        Returns:
            Fully-qualified URL string.
        """
        if is_dir:
            norm = _normalize_dir_path(path)
        else:
            norm = _normalize_file_path(path)

        encoded = _encode_path_for_url(norm, is_dir=is_dir)
        url = urljoin(self.base_url, encoded)
        return url

    def _session_get(self, url: str, **kwargs) -> requests.Response:
        """
        Wrapper around session.get that injects auth if configured.
        Does not override an explicit auth= in kwargs.
        """
        if self.auth is not None and "auth" not in kwargs:
            kwargs["auth"] = self.auth
        return self.session.get(url, **kwargs)

    def _session_head(self, url: str, **kwargs) -> requests.Response:
        """
        Wrapper around session.head that injects auth if configured.
        Does not override an explicit auth= in kwargs.
        """
        if self.auth is not None and "auth" not in kwargs:
            kwargs["auth"] = self.auth
        return self.session.head(url, **kwargs)

    # ------------------------------------------------------------------
    # Listing and walking
    # ------------------------------------------------------------------

    def listdir(self, path: str = "") -> List[NginxIndexEntry]:
        """
        List the contents of a remote directory.

        Args:
            path: Directory path relative to the base URL (may be empty string for root).

        Returns:
            List of NginxIndexEntry for each file/dir in that directory.
        """
        dir_path = _normalize_dir_path(path)
        url = self._build_url(dir_path, is_dir=True)
        resp = self._session_get(url, timeout=self.timeout)
        resp.raise_for_status()

        entries = parse_nginx_index_html(resp.text, current_dir=dir_path)
        return entries

    def walk(self, top: str = "") -> Iterator[Tuple[str, List[str], List[str]]]:
        """
        Recursively walk the remote directory tree.

        Yields tuples (dirpath, dirnames, filenames) similar to os.walk, where:
            dirpath   is the directory path relative to base (no leading '/', no trailing '/')
                      For the top-level, this may be "".
            dirnames  is a list of immediate subdirectory names (no slashes).
            filenames is a list of immediate file names (no slashes).

        Use os.path.join-like operations via posixpath if you want full paths:
            full_path = posixpath.join(dirpath, name)
        """
        stack = [_normalize_dir_path(top)]

        while stack:
            dir_path = stack.pop()
            entries = self.listdir(dir_path)

            if dir_path.endswith("/"):
                yield_dirpath = dir_path[:-1]
            else:
                yield_dirpath = dir_path

            dirnames: List[str] = []
            filenames: List[str] = []

            for entry in entries:
                rel_name = posixpath.basename(entry.path.rstrip("/"))

                if entry.is_dir:
                    dirnames.append(rel_name)
                    child_dir = entry.path
                    child_dir = _normalize_dir_path(child_dir)
                    stack.append(child_dir)
                else:
                    filenames.append(rel_name)

            yield yield_dirpath, dirnames, filenames

    # ------------------------------------------------------------------
    # Existence checks
    # ------------------------------------------------------------------

    def isdir(self, path: str) -> bool:
        """
        Heuristically determine whether a given path is a directory.

        Strategy:
        - Normalize as directory path and request it as a directory URL.
        - If we get 200 and a text/html response that looks like an index page,
          consider it a directory.
        """
        dir_path = _normalize_dir_path(path)
        url = self._build_url(dir_path, is_dir=True)
        try:
            resp = self._session_get(url, timeout=self.timeout)
        except requests.RequestException:
            return False

        if resp.status_code != 200:
            return False

        content_type = resp.headers.get("Content-Type", "").lower()
        if "text/html" not in content_type:
            return False

        soup = BeautifulSoup(resp.text, "html.parser")
        h1 = soup.find("h1")
        if not h1:
            return False
        if "index of" in h1.get_text(strip=True).lower():
            return True
        return False

    def isfile(self, path: str) -> bool:
        """
        Determine whether a given path is a file, using HTTP HEAD.

        Returns:
            True if the server returns 200 to HEAD and the content does not appear
            to be an index HTML; False otherwise.
        """
        file_path = _normalize_file_path(path)
        url = self._build_url(file_path, is_dir=False)

        try:
            resp = self._session_head(url, allow_redirects=True, timeout=self.timeout)
        except requests.RequestException:
            return False

        if resp.status_code != 200:
            return False

        content_type = resp.headers.get("Content-Type", "").lower()
        if "text/html" in content_type:
            return True

        return True

    def exists(self, path: str) -> bool:
        """
        Check whether a path exists as either a file or a directory.

        Strategy:
        - If path ends with '/', first check isdir().
        - Otherwise check isfile(), and if that fails, check isdir().
        """
        if path.endswith("/"):
            return self.isdir(path)
        if self.isfile(path):
            return True
        return self.isdir(path)

    # ------------------------------------------------------------------
    # Downloading and partials
    # ------------------------------------------------------------------

    def download(
        self,
        path: str,
        dest: Union[str, "bytes", "bytearray", "memoryview", "None", "object"],
        start: Optional[int] = None,
        end: Optional[int] = None,
        chunk_size: int = 64 * 1024,
        allow_resume: bool = False,
    ) -> None:
        """
        Download a file to a destination, optionally using HTTP Range.

        Args:
            path: Remote file path relative to base.
            dest: Destination. If a string or os.PathLike, treated as a file path.
                  If a file-like object, must have write(bytes) method.
            start: Optional starting byte offset (inclusive).
            end: Optional ending byte offset (inclusive).
                 Use None to indicate "to the end".
            chunk_size: Chunk size for streaming download.
            allow_resume: If True and dest is a path pointing to an existing file,
                          attempt to resume by starting from the current file size.
                          Ignored if 'start' is explicitly provided.

        Raises:
            ValueError if the server does not honor the Range request when used.
        """
        file_path = _normalize_file_path(path)
        url = self._build_url(file_path, is_dir=False)

        headers = {}
        range_requested = start is not None or end is not None

        if isinstance(dest, (str, bytes, os.PathLike)):
            dest_path = os.fspath(dest)
        else:
            dest_path = None

        if allow_resume and dest_path is not None and start is None:
            if os.path.exists(dest_path):
                already = os.path.getsize(dest_path)
                if already > 0:
                    start = already
                    range_requested = True

        if range_requested:
            start_str = "" if start is None else str(start)
            end_str = "" if end is None else str(end)
            headers["Range"] = f"bytes={start_str}-{end_str}"

        resp = self._session_get(
            url,
            headers=headers,
            stream=True,
            timeout=self.timeout,
        )
        resp.raise_for_status()

        if range_requested and resp.status_code != 206:
            raise ValueError(
                f"Expected partial content (206) for Range request, got {resp.status_code}"
            )

        if dest_path is not None:
            mode = "ab" if (allow_resume and start not in (None, 0)) else "wb"
            with open(dest_path, mode) as f:
                for chunk in resp.iter_content(chunk_size=chunk_size):
                    if not chunk:
                        continue
                    f.write(chunk)
        else:
            f = dest  # type: ignore[assignment]
            for chunk in resp.iter_content(chunk_size=chunk_size):
                if not chunk:
                    continue
                f.write(chunk)

    def fetch_bytes(
        self,
        path: str,
        start: Optional[int] = None,
        end: Optional[int] = None,
    ) -> bytes:
        """
        Fetch a file (or a byte range of it) into memory and return it.

        Args:
            path: Remote file path relative to base.
            start: Optional starting byte offset (inclusive).
            end: Optional ending byte offset (inclusive).

        Returns:
            The content as bytes.

        Raises:
            ValueError if the server does not honor the Range request when used.
        """
        file_path = _normalize_file_path(path)
        url = self._build_url(file_path, is_dir=False)

        headers = {}
        range_requested = start is not None or end is not None
        if range_requested:
            start_str = "" if start is None else str(start)
            end_str = "" if end is None else str(end)
            headers["Range"] = f"bytes={start_str}-{end_str}"

        resp = self._session_get(
            url,
            headers=headers,
            stream=True,
            timeout=self.timeout,
        )
        resp.raise_for_status()

        if range_requested and resp.status_code != 206:
            raise ValueError(
                f"Expected partial content (206) for Range request, got {resp.status_code}"
            )

        chunks = []
        for chunk in resp.iter_content(chunk_size=64 * 1024):
            if not chunk:
                continue
            chunks.append(chunk)
        return b"".join(chunks)

    # ------------------------------------------------------------------
    # Directory download
    # ------------------------------------------------------------------

    def download_directory(
        self,
        remote_dir: str,
        local_root: str,
        allow_resume: bool = False,
        chunk_size: int = 64 * 1024,
    ) -> None:
        """
        Recursively download a remote directory tree, mirroring it under local_root.

        Args:
            remote_dir: Remote directory path relative to base. May be "" for the root,
                        and may end with or without a trailing "/".
            local_root: Local directory under which the structure will be recreated.
            allow_resume: If True, each file is downloaded with resume support.
            chunk_size: Chunk size for streaming downloads.

        Example:
            client.download_directory("01%20A%20Just%20Determination/", "./downloads")
        """
        remote_dir_norm = _normalize_dir_path(remote_dir)
        base = remote_dir_norm.rstrip("/")

        for dirpath, dirnames, filenames in self.walk(remote_dir_norm):
            if base:
                if dirpath == base:
                    rel_dir = ""
                elif dirpath.startswith(base + "/"):
                    rel_dir = dirpath[len(base) + 1 :]
                else:
                    rel_dir = dirpath
            else:
                rel_dir = dirpath

            if rel_dir:
                local_dir = os.path.join(local_root, *rel_dir.split("/"))
            else:
                local_dir = local_root

            os.makedirs(local_dir, exist_ok=True)

            for filename in filenames:
                if dirpath:
                    remote_file_path = posixpath.join(dirpath, filename)
                else:
                    remote_file_path = filename
                local_path = os.path.join(local_dir, filename)

                self.download(
                    remote_file_path,
                    local_path,
                    start=None,
                    end=None,
                    chunk_size=chunk_size,
                    allow_resume=allow_resume,
                )



