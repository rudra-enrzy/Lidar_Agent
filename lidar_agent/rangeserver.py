"""SimpleHTTPRequestHandler + HTTP Range support.
Potree 2.0 (PotreeConverter 2.x output) reads octree.bin / hierarchy.bin with 'Range: bytes=a-b' requests.
Python's built-in handler ignores Range and sends the whole file, so Potree decodes garbage and draws nothing."""
import os, re, http.server


class RangeRequestHandler(http.server.SimpleHTTPRequestHandler):
    _left = None

    def send_head(self):
        rng = self.headers.get("Range")
        path = self.translate_path(self.path)
        if not rng or not path or os.path.isdir(path):
            return super().send_head()
        m = re.match(r"bytes=(\d*)-(\d*)$", rng.strip())
        if not m:
            return super().send_head()
        try:
            f = open(path, "rb")
        except OSError:
            self.send_error(404, "File not found"); return None
        size = os.fstat(f.fileno()).st_size
        a, b = m.groups()
        if a == "":
            start, end = max(0, size - int(b or 0)), size - 1
        else:
            start, end = int(a), (int(b) if b else size - 1)
        end = min(end, size - 1)
        if start >= size or start > end:
            f.close()
            self.send_response(416); self.send_header("Content-Range", f"bytes */{size}"); self.end_headers()
            return None
        self.send_response(206)
        self.send_header("Content-Type", self.guess_type(path))
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        self.send_header("Content-Length", str(end - start + 1))
        self.end_headers()
        f.seek(start)
        self._left = end - start + 1
        return f

    def copyfile(self, src, dst):
        if self._left is None:
            return super().copyfile(src, dst)
        left = self._left
        while left > 0:
            chunk = src.read(min(1 << 20, left))
            if not chunk: break
            dst.write(chunk); left -= len(chunk)
        self._left = None
