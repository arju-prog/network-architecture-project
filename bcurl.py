#!/usr/bin/env python3
"""bcurl - a BHTTP/1 client (see SPEC.md).

Usage: ./bcurl.py [-v] [-I] [-H 'name: value']... HOST:PORT/PATH [HOST:PORT/PATH ...]
  -v   hexdump every frame sent (>) and received (<) to stderr
  -I   send HEAD instead of GET
  -H   add a request header (may repeat)
All URLs must name the same host:port; they share ONE connection.
Exit status: 0 = all OK, 1 = some response was 4xx/5xx, 2 = usage/network/protocol error.
Author: Arjun (24bcs10109)
"""
import socket
import struct
import sys

# ---- protocol constants (SPEC.md sections 2-5) ----
HDR_LEN = 5
T_REQUEST, T_RESPONSE, T_DATA = 0x01, 0x02, 0x03
F_END = 0x01
M_GET, M_HEAD = 0x01, 0x02
STATIC = [None, "host", "user-agent", "accept", "connection", "server",
          "date", "content-type", "content-length", "last-modified", "etag"]
INDEX = {name: i for i, name in enumerate(STATIC) if name}
TYPE_NAME = {T_REQUEST: "REQUEST", T_RESPONSE: "RESPONSE", T_DATA: "DATA"}

verbose = False


def die(msg):
    print(f"bcurl: {msg}", file=sys.stderr)
    sys.exit(2)


def hexdump(direction, frame):
    if not verbose:
        return
    t = frame[3]
    name = TYPE_NAME.get(t, f"UNKNOWN(0x{t:02x})")
    print(f"{direction} [{name} length={len(frame) - HDR_LEN} flags=0x{frame[4]:02x}]",
          file=sys.stderr)
    for off in range(0, len(frame), 16):
        row = frame[off:off + 16]
        hexs = " ".join(f"{b:02x}" for b in row)
        text = "".join(chr(b) if 32 <= b < 127 else "." for b in row)
        print(f"{direction} {off:04x}  {hexs:<47}  |{text}|", file=sys.stderr)


def read_exact(sock, n):
    buf = bytearray()
    while len(buf) < n:
        part = sock.recv(n - len(buf))
        if not part:
            die("connection closed by server mid-response")
        buf += part
    return bytes(buf)


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
    headers, i = [], 0
    try:
        while i < len(buf):
            idx = buf[i]
            i += 1
            if idx == 0:
                nlen = buf[i]
                name = buf[i + 1:i + 1 + nlen].decode("ascii")
                if nlen == 0 or len(name) != nlen:
                    raise ValueError
                i += 1 + nlen
            else:
                name = STATIC[idx] if idx < len(STATIC) else None
            (vlen,) = struct.unpack_from("!H", buf, i)
            value = buf[i + 2:i + 2 + vlen]
            if len(value) != vlen:
                raise ValueError
            i += 2 + vlen
            if name:
                headers.append((name, value.decode("utf-8")))
    except (IndexError, ValueError, struct.error):
        die("malformed header block in response")
    return headers


def parse_url(url):
    for scheme in ("bhttp://", "http://"):
        if url.startswith(scheme):
            url = url[len(scheme):]
    hostport, slash, path = url.partition("/")
    host, _, port = hostport.rpartition(":")
    if not host or not port.isdigit():
        die(f"bad URL '{url}' (expected HOST:PORT/PATH)")
    return host, int(port), "/" + path


def fetch(sock, method, path, headers):
    """Send one REQUEST, write the body to stdout, return the status."""
    p = path.encode("utf-8")
    payload = bytes([method]) + struct.pack("!H", len(p)) + p + encode_headers(headers)
    frame = len(payload).to_bytes(3, "big") + bytes([T_REQUEST, 0]) + payload
    hexdump(">", frame)
    sock.sendall(frame)

    status = None
    while True:
        hdr = read_exact(sock, HDR_LEN)
        length, ftype, flags = int.from_bytes(hdr[:3], "big"), hdr[3], hdr[4]
        body = read_exact(sock, length)
        hexdump("<", hdr + body)
        if ftype == T_RESPONSE and status is None:
            if length < 2:
                die("RESPONSE frame too short")
            (status,) = struct.unpack_from("!H", body, 0)
            if verbose:
                print(f"< status {status}", file=sys.stderr)
                for name, value in decode_headers(body[2:]):
                    print(f"< {name}: {value}", file=sys.stderr)
            else:
                decode_headers(body[2:])
            if flags & F_END:
                return status
        elif ftype == T_DATA and status is not None:
            sys.stdout.buffer.write(body)
            if flags & F_END:
                sys.stdout.buffer.flush()
                return status
        elif ftype in TYPE_NAME:
            die(f"unexpected {TYPE_NAME[ftype]} frame")
        # any other type: unknown, already read in full -> skipped


def main():
    global verbose
    args, method, extra, urls = sys.argv[1:], M_GET, [], []
    while args:
        a = args.pop(0)
        if a == "-v":
            verbose = True
        elif a == "-I":
            method = M_HEAD
        elif a == "-H":
            if not args or ":" not in args[0]:
                die("-H needs 'name: value'")
            name, _, value = args.pop(0).partition(":")
            extra.append((name.strip().lower(), value.strip()))
        else:
            urls.append(a)
    if not urls:
        print(__doc__, file=sys.stderr)
        sys.exit(2)

    targets = [parse_url(u) for u in urls]
    host, port = targets[0][:2]
    if any(t[:2] != (host, port) for t in targets):
        die("all URLs must use the same host:port (bcurl never opens a second connection)")

    try:
        sock = socket.create_connection((host, port), timeout=30)
    except OSError as e:
        die(f"cannot connect to {host}:{port}: {e}")

    worst = 0
    with sock:
        for i, (_, _, path) in enumerate(targets):
            headers = [("host", f"{host}:{port}"), ("user-agent", "bcurl/1.0"),
                       ("accept", "*/*")] + extra
            if i == len(targets) - 1:
                headers.append(("connection", "close"))
            try:
                status = fetch(sock, method, path, headers)
            except OSError as e:
                die(f"network error: {e}")
            worst = max(worst, status)
    sys.exit(1 if worst >= 400 else 0)


if __name__ == "__main__":
    main()
