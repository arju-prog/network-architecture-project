# BHTTP/1 — HTTP, in binary

**Arjun · Roll No. 24BCS10109 · Network Architecture course project**

BHTTP/1 is a small binary version of HTTP. Requests and responses travel as
length-prefixed frames instead of text lines, and common header names are sent as
one-byte numbers. The repo contains the protocol spec, a file server (`bserve.py`), a
client (`bcurl.py`) and an annotated hexdump of a real exchange.

Requires only Python 3, with no packages to install.

## What's in the repo

| File | Hand-in | What it is |
|------|---------|------------|
| [`SPEC.md`](SPEC.md) | 1 | The protocol spec: enough for a stranger to build either side |
| [`bserve.py`](bserve.py) | 2 | Server: serves files from a folder over BHTTP/1 |
| [`bcurl.py`](bcurl.py) | 2 | Client: fetches files, with an optional hexdump of every frame |
| [`HEXDUMP.md`](HEXDUMP.md) | 3 | One complete request and response, annotated byte by byte |
| [`test.py`](test.py) | — | Tests that send raw bytes and check the replies |
| [`www/`](www) | — | Sample files to serve |

## Quick start

```sh
# terminal 1: serve the www folder on port 9000
./bserve.py ./www 9000

# terminal 2
./bcurl.py localhost:9000/index.html               # body to stdout
./bcurl.py -v localhost:9000/index.html            # also hexdump every frame to stderr
./bcurl.py -I localhost:9000/style.css             # HEAD: headers only
./bcurl.py localhost:9000/ localhost:9000/style.css   # 2 requests, 1 connection
./bcurl.py localhost:9000/missing; echo $?         # 404, exit status 1
./test.py 9000                                     # run the tests
```

> If port 9000 is busy (Docker often uses it), pick another port, e.g. `9100`.

Example `-v` output (`>` = sent, `<` = received):

```
> [REQUEST length=57 flags=0x00]
> 0000  00 00 39 01 00 01 00 0b 2f 69 6e 64 65 78 2e 68  |..9...../index.h|
...
< [RESPONSE length=121 flags=0x00]
< status 200
< content-length: 182
< content-type: text/html
...
< [DATA length=182 flags=0x01]
```

## The protocol at a glance

Every frame starts with the same **5-byte header**:

```
+--------+--------+--------+--------+--------+---------------------+
|        Length (24 bits)  |  Type  | Flags  | Payload (Length B)  |
+--------+--------+--------+--------+--------+---------------------+
```

| Type | Frame | Payload |
|------|-------|---------|
| `0x01` | REQUEST | method (1 byte) · path length (2) · path · headers |
| `0x02` | RESPONSE | status (2 bytes) · headers |
| `0x03` | DATA | body bytes. The last one has the END flag (`0x01`) set |
| other | unknown | **must be skipped** by reading `Length` bytes. This leaves room for version 2 |

**Headers:** the ten names we actually send get a one-byte number. Any other name is sent
as text, with its length in front.

| 1 host | 2 user-agent | 3 accept | 4 connection | 5 server |
|---|---|---|---|---|
| **6 date** | **7 content-type** | **8 content-length** | **9 last-modified** | **10 etag** |

### Why 24 / 8 / 8 and no stream ID?

HTTP/2 uses a 9-byte header split 24 / 8 / 8 / 31. BHTTP/1 keeps the first three fields
and drops the 31-bit stream ID.
- **Length, 24 bits:** up to 16 MiB per frame, so neither the 64 KiB cap of 16 bits nor
  the wasted byte of 32 bits. Bodies are still split into DATA frames of at most 16 KiB.
- **Type, 8 bits:** 3 types used and 253 spare for future versions.
- **Flags, 8 bits:** only END is used today, and a full byte keeps the header aligned.
- **No stream ID:** only one request is in flight per connection, so responses come back
  in order and a stream ID would cost 4 bytes per frame for nothing.

Because the length always comes first, a receiver can always find where the next frame
starts. So the server can answer a broken request with **400** and keep the connection open.

Full details are in [`SPEC.md`](SPEC.md).

## Behaviour

**Server: `bserve.py ROOT PORT`**
- Keeps each connection open for more requests, and handles several clients at once.
- Maps the request path to a file under `ROOT`. A path ending in `/` serves `index.html`,
  and `../` escapes are blocked.
- Replies **200** with the file, **404** if it isn't there, **400** if the frame is
  malformed, **405** for an unknown method, and **500** if the file can't be read.

**Client: `bcurl.py [-v] [-I] [-H 'name: value'] HOST:PORT/PATH ...`**
- Builds the binary request and writes the response body to stdout.
- With `-v`, hexdumps every frame to stderr.
- Fetches all URLs over **one** connection and never opens a second one.
- Exit status: `0` OK, `1` if any response was 4xx/5xx, `2` for a usage, network or
  protocol error.

## Tests

`test.py` builds frames from raw bytes, using only the spec. It checks that:
- a malformed REQUEST gets **400**;
- the same connection then still serves a **200**;
- DATA frames carry the exact file bytes;
- the server and the client both **skip unknown frame types**.

```
$ ./test.py 9000
PASS malformed REQUEST gets 400
PASS same connection still serves 200 after 400
PASS DATA frames carry the file
PASS bcurl skips unknown frame types
all tests passed
```
