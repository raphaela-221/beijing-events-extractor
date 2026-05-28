"""
Simplified file reading utilities — no Coze dependencies.
Supports local file paths and HTTP/HTTPS URLs.
"""
import os
import logging
from io import BytesIO
from urllib.parse import urlparse, unquote
from typing import Tuple, Optional

import requests

logger = logging.getLogger(__name__)

MAX_FILE_SIZE = 100 * 1024 * 1024  # 100MB


def read_file_bytes(path_or_url: str) -> Tuple[bytes, str, str]:
    """
    Read file content as bytes.

    Returns:
        (content_bytes, filename, extension)
    """
    path_or_url = path_or_url.strip()

    if path_or_url.startswith(('http://', 'https://')):
        return _read_url(path_or_url)
    else:
        return _read_local(path_or_url)


def _read_url(url: str) -> Tuple[bytes, str, str]:
    """Download file from URL with streaming and size limit."""
    filename = extract_filename_from_url(url)
    _, ext = infer_extension(filename)

    try:
        with requests.get(url, stream=True, timeout=120) as resp:
            resp.raise_for_status()

            content_length = resp.headers.get('Content-Length')
            if content_length and int(content_length) > MAX_FILE_SIZE:
                raise RuntimeError(
                    f"File size ({int(content_length)} bytes) exceeds 100MB limit."
                )

            downloaded = BytesIO()
            current_size = 0
            for chunk in resp.iter_content(chunk_size=8192):
                if chunk:
                    current_size += len(chunk)
                    if current_size > MAX_FILE_SIZE:
                        raise RuntimeError("File exceeds 100MB limit during download.")
                    downloaded.write(chunk)

            return downloaded.getvalue(), filename, ext

    except requests.RequestException as e:
        raise RuntimeError(f"Failed to download {url}: {e}")


def _read_local(path: str) -> Tuple[bytes, str, str]:
    """Read local file."""
    if not os.path.exists(path):
        raise FileNotFoundError(f"File not found: {path}")

    filename = os.path.basename(path)
    _, ext = infer_extension(filename)

    with open(path, 'rb') as f:
        content = f.read()

    return content, filename, ext


def extract_filename_from_url(url: str) -> str:
    """Extract readable filename from URL, handling URL encoding and query params."""
    path = urlparse(url).path
    fname = path.rsplit("/", 1)[-1] if "/" in path else path
    try:
        fname = unquote(fname)
    except Exception:
        pass
    return fname


def infer_extension(filename: str) -> Tuple[str, str]:
    """
    Infer file category and extension from filename.

    Returns:
        (category, extension_with_dot)  e.g. ('document', '.xlsx')
    """
    _, ext_with_dot = os.path.splitext(filename)

    if not ext_with_dot:
        return 'default', ""

    ext = ext_with_dot.lstrip('.').lower()

    TYPE_MAPPING = {
        'image': {'apng', 'avif', 'bmp', 'gif', 'heic', 'ico', 'jpg', 'jpeg', 'png', 'svg', 'tiff', 'webp'},
        'video': {'mp4', 'avi', 'mov', 'mkv', 'flv', 'wmv', 'webm', 'm4v', '3gp'},
        'audio': {'mp3', 'wav', 'flac', 'aac', 'ogg', 'wma', 'm4a'},
        'document': {'pdf', 'doc', 'docx', 'xls', 'xlsx', 'ppt', 'pptx', 'txt', 'md', 'csv', 'json', 'xml', 'html', 'htm'},
    }

    for category, extensions in TYPE_MAPPING.items():
        if ext in extensions:
            return category, ext_with_dot

    return 'default', ext_with_dot
