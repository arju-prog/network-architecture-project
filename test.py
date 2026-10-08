#!/usr/bin/env python3
"""Raw-byte tests for BHTTP/1, written only from SPEC.md (no shared code).

Usage: ./test.py PORT      (with ./bserve.py ./www PORT already running)
"""
import socket
import subprocess
import sys
import threading

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 9000


def frame(ftype, flags, payload):
    return len(payload).to_bytes(3, "big") + bytes([ftype, flags]) + payload


def read_frame(s):
    hdr = s.recv(5, socket.MSG_WAITALL)
    length = int.from_bytes(hdr[:3], "big")
    return hdr[3], hdr[4], s.recv(length, socket.MSG_WAITALL) if length else b""


def check(name, ok):
    print(("PASS " if ok else "FAIL ") + name)
    if not ok:
        sys.exit(1)


# 1. Server: unknown frame skipped, malformed frame -> 400, connection stays open.
s = socket.create_connection(("127.0.0.1", PORT))
s.sendall(frame(0x7F, 0, b"future stuff"))                  # unknown type
s.sendall(frame(0x01, 0, b"\x01\x00\xff/x"))                 # path length 255 > 2 bytes left
t, f, p = read_frame(s)
check("malformed REQUEST gets 400", t == 0x02 and p[:2] == (400).to_bytes(2, "big"))
if not f & 1:
    while not read_frame(s)[1] & 1:                          # drain the 400 body
        pass
path = b"/index.html"
s.sendall(frame(0x01, 0, b"\x01" + len(path).to_bytes(2, "big") + path))
t, f, p = read_frame(s)
check("same connection still serves 200 after 400", t == 0x02 and p[:2] == b"\x00\xc8")
body = b""
while True:
    t, f, p = read_frame(s)
    body += p
    if f & 1:
        break
check("DATA frames carry the file", body == open("www/index.html", "rb").read())
s.close()

# 2. Client: unknown frame types from the server are skipped.
fake = socket.socket()
fake.bind(("127.0.0.1", 0))
fake.listen(1)


def fake_server():
    c, _ = fake.accept()
    hdr = c.recv(5, socket.MSG_WAITALL)
    c.recv(int.from_bytes(hdr[:3], "big"), socket.MSG_WAITALL)
    c.sendall(frame(0x42, 0, b"ignore me") +
              frame(0x02, 0, b"\x00\xc8") +
              frame(0x99, 0, b"") +
              frame(0x03, 1, b"hi\n"))
    c.close()


threading.Thread(target=fake_server, daemon=True).start()
out = subprocess.run(["./bcurl.py", f"127.0.0.1:{fake.getsockname()[1]}/"], capture_output=True)
check("bcurl skips unknown frame types", out.returncode == 0 and out.stdout == b"hi\n")
print("all tests passed")
