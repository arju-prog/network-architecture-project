#!/usr/bin/env python3
"""bserve - a BHTTP/1 file server (see SPEC.md).

Usage: ./bserve.py ROOT PORT
Author: Arjun (24bcs10109)
"""
import os
import socketserver
import struct
import sys
import mimetypes
from email.utils import formatdate

# ---- protocol constants (SPEC.md sections 2-5) ----
HDR_LEN = 5
T_REQUEST, T_RESPONSE, T_DATA = 0x01, 0x02, 0x03
F_END = 0x01
M_GET, M_HEAD = 0x01, 0x02
STATIC = [None, "host", "user-agent", "accept", "connection", "server",
          "date", "content-type", "content-length", "last-modified", "etag"]
INDEX = {name: i for i, name in enumerate(STATIC) if name}
CHUNK = 16384          # max DATA payload we send
MAX_REQUEST = 65536    # largest REQUEST payload we accept
REASON = {200: "OK", 400: "Bad Request", 404: "Not Found",
          405: "Method Not Allowed", 500: "Internal Server Error"}


def read_exact(sock, n):
    """Read exactly n bytes, or return None if the peer closed first."""
    buf = bytearray()
    while len(buf) < n:
        part = sock.recv(n - len(buf))
        if not part:
            return None
        buf += part
    return bytes(buf)


def skip(sock, n):
    """Discard n payload bytes without buffering them all."""
    while n > 0:
        part = sock.recv(min(n, 65536))
        if not part:
            return False
        n -= len(part)
    return True


def send_frame(sock, ftype, flags, payload=b""):
    sock.sendall(len(payload).to_bytes(3, "big") + bytes([ftype, flags]) + payload)


def encode_headers(headers):
    out = bytearray()
    for name, value in headers:
        v = value.encode("utf-8")
        idx = INDEX.get(name)
        if idx:
            out.append(idx)
        else:
            n = name.encode("ascii")
            out += bytes([0, len(n)]) + n
        out += struct.pack("!H", len(v)) + v
    return bytes(out)


def decode_headers(buf):
    """Parse a header block. Raises ValueError if it is malformed."""
    headers, i = [], 0
    while i < len(buf):
        idx = buf[i]
        i += 1
        if idx == 0:
            if i >= len(buf) or buf[i] == 0:
                raise ValueError("bad literal name length")
            nlen = buf[i]
            i += 1
            if i + nlen > len(buf):
                raise ValueError("truncated name")
            name = buf[i:i + nlen].decode("ascii").lower()
            i += nlen
        else:
            name = STATIC[idx] if idx < len(STATIC) else None  # unknown index: ignore
        if i + 2 > len(buf):
            raise ValueError("truncated value length")
        (vlen,) = struct.unpack_from("!H", buf, i)
        i += 2
        if i + vlen > len(buf):
            raise ValueError("truncated value")
        value = buf[i:i + vlen].decode("utf-8")
        i += vlen
        if name:
            headers.append((name, value))
    return headers


def parse_request(p):
    if len(p) < 3:
        raise ValueError("short request")
    method = p[0]
    (plen,) = struct.unpack_from("!H", p, 1)
    if 3 + plen > len(p):
        raise ValueError("truncated path")
    path = p[3:3 + plen].decode("utf-8")
    if not path.startswith("/") or "\0" in path:
        raise ValueError("bad path")
    return method, path, decode_headers(p[3 + plen:])


def resolve(root, path):
    """Map a request path to a file under root, or None."""
    path = path.split("?", 1)[0]
    if path.endswith("/"):
        path += "index.html"
    full = os.path.realpath(os.path.join(root, path.lstrip("/")))
    if not full.startswith(root + os.sep):   # blocks ../ escapes
        return None
    return full if os.path.isfile(full) else None


class Handler(socketserver.BaseRequestHandler):
    def handle(self):
        try:
            self.loop()
        except (ConnectionError, OSError):
            pass

    def loop(self):
        sock = self.request
        while True:                                   # keep the connection open
            hdr = read_exact(sock, HDR_LEN)
            if hdr is None:
                return
            length, ftype = int.from_bytes(hdr[:3], "big"), hdr[3]

            if ftype != T_REQUEST:
                if not skip(sock, length):
                    return
                if ftype in (T_RESPONSE, T_DATA):     # known, but wrong here
                    self.reply(0, 400, "-", b"unexpected frame type\n")
                continue                              # unknown type: skip silently

            if length > MAX_REQUEST:
                if not skip(sock, length):
                    return
                self.reply(0, 400, "-", b"request frame too large\n")
                continue

            payload = read_exact(sock, length)
            if payload is None:
                return
            try:
                method, path, headers = parse_request(payload)
            except ValueError as e:
                self.reply(0, 400, "-", f"malformed request: {e}\n".encode())
                continue

            close = dict(headers).get("connection", "").lower() == "close"
            self.serve(method, path, close)
            if close:
                return

    def serve(self, method, path, close):
        if method not in (M_GET, M_HEAD):
            return self.reply(M_GET, 405, path, b"405 Method Not Allowed\n", close=close)
        full = resolve(self.server.root, path)
        if full is None:
            return self.reply(method, 404, path, b"404 Not Found\n", close=close)
        try:
            with open(full, "rb") as f:
                body = f.read()
            st = os.stat(full)
        except OSError:
            return self.reply(method, 500, path, b"500 Internal Server Error\n", close=close)
        ctype = mimetypes.guess_type(full)[0] or "application/octet-stream"
        extra = [("content-type", ctype),
                 ("last-modified", formatdate(st.st_mtime, usegmt=True)),
                 ("etag", '"%x-%x"' % (st.st_size, int(st.st_mtime)))]
        self.reply(method, 200, path, body, extra, close)

    def reply(self, method, status, path, body, extra=None, close=False):
        if extra is None:
            extra = [("content-type", "text/plain")]
        headers = [("server", "bserve/1.0"),
                   ("date", formatdate(usegmt=True)),
                   ("content-length", str(len(body)))] + extra
        if close:
            headers.append(("connection", "close"))
        send_body = method != M_HEAD and len(body) > 0
        payload = struct.pack("!H", status) + encode_headers(headers)
        send_frame(self.request, T_RESPONSE, 0 if send_body else F_END, payload)
        if send_body:
            for off in range(0, len(body), CHUNK):
                last = off + CHUNK >= len(body)
                send_frame(self.request, T_DATA, F_END if last else 0, body[off:off + CHUNK])
        name = {M_GET: "GET", M_HEAD: "HEAD"}.get(method, "?")
        print(f'{self.client_address[0]} "{name} {path}" {status} {len(body)}',
              file=sys.stderr, flush=True)


class Server(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


def main():
    if len(sys.argv) != 3 or not sys.argv[2].isdigit():
        sys.exit("usage: bserve.py ROOT PORT")
    root = os.path.realpath(sys.argv[1])
    if not os.path.isdir(root):
        sys.exit(f"bserve: {sys.argv[1]} is not a directory")
    with Server(("", int(sys.argv[2])), Handler) as srv:
        srv.root = root
        print(f"bserve: serving {root} on port {sys.argv[2]}", file=sys.stderr, flush=True)
        try:
            srv.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
