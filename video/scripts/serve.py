#!/usr/bin/env python3
"""Serve an explicitly reviewed export on loopback with video byte ranges.

The server answers only below a secret path prefix, /<key>/. Every other path
returns 404, so the tunnel URL alone does not give access to the export.
"""

import argparse
import functools
import hmac
import os
import secrets
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import re
from urllib.parse import unquote, urlsplit


KEY_PATTERN = re.compile(r"[A-Za-z0-9_-]{32,}")


class ExportHandler(SimpleHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def __init__(self, *args, key, **kwargs):
        self.key = key
        super().__init__(*args, **kwargs)

    def log_message(self, format, *args):
        # Keep the access key out of the server log.
        super().log_message("%s", (format % args).replace(self.key, "<key>"))

    def translate_path(self, path):
        # send_head accepts only paths below /<key>/, so remove that prefix here.
        prefix = f"/{self.key}"
        if path.startswith(prefix):
            path = path[len(prefix):] or "/"
        return super().translate_path(path)

    def key_matches(self):
        segments = urlsplit(self.path).path.split("/", 2)
        return len(segments) >= 2 and hmac.compare_digest(segments[1].encode(), self.key.encode())

    def list_directory(self, path):
        self.send_error(403, "Directory listings disabled")
        return None

    def end_headers(self):
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Cache-Control", "no-store")
        # The key is in the URL path. Do not send it to other sites or to search engines.
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("X-Robots-Tag", "noindex, nofollow")
        self.send_header("X-Content-Type-Options", "nosniff")
        super().end_headers()

    def send_head(self):
        self.remaining = None
        if not self.key_matches():
            self.send_error(404, "Not found")
            return None
        if urlsplit(self.path).path == f"/{self.key}":
            self.send_response(301)
            self.send_header("Location", f"/{self.key}/")
            self.send_header("Content-Length", "0")
            self.end_headers()
            return None
        lexical_root = Path(self.directory).absolute()
        root = lexical_root.resolve()
        # Reject hidden/traversal paths and symlinks, even to files inside root.
        parts = Path(unquote(urlsplit(self.path).path)).parts
        if any(part.startswith(".") for part in parts if part != "/"):
            self.send_error(403, "Path is not part of the export")
            return None
        try:
            relative = Path(self.translate_path(self.path)).absolute().relative_to(lexical_root)
            path = root / relative
            candidate = root
            for part in relative.parts:
                candidate = candidate / part
                if candidate.is_symlink():
                    raise ValueError("symlink")
            path.resolve().relative_to(root)
        except (ValueError, OSError):
            self.send_error(403, "Path is not part of the export")
            return None
        # Directory index must pass the same symlink protection.
        if path.is_dir():
            for name in ("index.html", "index.htm"):
                if (path / name).is_symlink():
                    self.send_error(403, "Symlinks are not exported")
                    return None
        header = self.headers.get("Range")
        if not header or not path.is_file():
            return super().send_head()
        size = path.stat().st_size
        match = re.fullmatch(r"bytes=(\d*)-(\d*)", header.strip())
        if not match or not any(match.groups()):
            return self.invalid_range(size)
        first, last = match.groups()
        if first:
            start = int(first)
            end = int(last) if last else size - 1
        else:
            suffix = int(last)
            if suffix == 0:
                return self.invalid_range(size)
            start = max(0, size - suffix)
            end = size - 1
        if start >= size or start > end or size == 0:
            return self.invalid_range(size)
        end = min(end, size - 1)
        try:
            handle = path.open("rb")
        except OSError:
            self.send_error(404, "File unavailable")
            return None
        handle.seek(start)
        self.send_response(206)
        self.send_header("Content-Type", self.guess_type(str(path)))
        self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        self.send_header("Content-Length", str(end - start + 1))
        self.end_headers()
        self.remaining = end - start + 1
        return handle

    def invalid_range(self, size):
        self.send_response(416)
        self.send_header("Content-Range", f"bytes */{size}")
        self.send_header("Content-Length", "0")
        self.end_headers()
        return None

    def copyfile(self, source, outputfile):
        if self.remaining is None:
            return super().copyfile(source, outputfile)
        while self.remaining > 0:
            chunk = source.read(min(65536, self.remaining))
            if not chunk:
                break
            outputfile.write(chunk)
            self.remaining -= len(chunk)


def load_key(key_file, root):
    """Read the key from key_file, or make a new key and write it there."""
    if key_file is None:
        return secrets.token_urlsafe(32)
    key_file = key_file.expanduser().absolute()
    if key_file.resolve().is_relative_to(root.resolve()):
        raise SystemExit("The key file must be outside the export directory")
    if key_file.exists():
        key = key_file.read_text().strip()
        if not KEY_PATTERN.fullmatch(key):
            raise SystemExit("The key file must hold at least 32 URL-safe characters")
        return key
    key = secrets.token_urlsafe(32)
    descriptor = os.open(key_file, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w") as handle:
        handle.write(key + "\n")
    return key


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path, help="Reviewed export directory, never a private run directory")
    parser.add_argument("--port", type=int, default=8837)
    parser.add_argument(
        "--key-file",
        type=Path,
        help="Private file (mode 600, outside the export) that keeps the access key across restarts",
    )
    args = parser.parse_args()
    root = args.directory.resolve(strict=True)
    if not root.is_dir():
        parser.error("Export must be a directory")
    key = load_key(args.key_file, root)
    handler = functools.partial(ExportHandler, directory=str(root), key=key)
    with ThreadingHTTPServer(("127.0.0.1", args.port), handler) as server:
        print(f"Key-protected export server: http://127.0.0.1:{server.server_port}/{key}/", flush=True)
        server.serve_forever()


if __name__ == "__main__":
    main()
