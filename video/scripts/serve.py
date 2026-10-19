#!/usr/bin/env python3
"""Serve an explicitly reviewed export on loopback with video byte ranges."""

import argparse
import functools
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import re
from urllib.parse import unquote, urlsplit


class ExportHandler(SimpleHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def list_directory(self, path):
        self.send_error(403, "Directory listings disabled")
        return None

    def end_headers(self):
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        super().end_headers()

    def send_head(self):
        self.remaining = None
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


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path, help="Reviewed public export, never a private run directory")
    parser.add_argument("--port", type=int, default=8837)
    args = parser.parse_args()
    root = args.directory.resolve(strict=True)
    if not root.is_dir():
        parser.error("Export must be a directory")
    handler = functools.partial(ExportHandler, directory=str(root))
    with ThreadingHTTPServer(("127.0.0.1", args.port), handler) as server:
        print(f"Public export server: http://127.0.0.1:{server.server_port}/", flush=True)
        server.serve_forever()


if __name__ == "__main__":
    main()
