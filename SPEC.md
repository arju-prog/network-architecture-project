# BHTTP/1 — HTTP, in binary

**Arjun · Roll No. 24bcs10109 · Network Architecture course project**

BHTTP/1 carries HTTP-style GET/HEAD requests over a single TCP connection using
binary frames in place of text lines. This document is the whole contract: a
client and a server written from it by different people must interoperate.

## 1. Connection model

- The client opens one TCP connection to the server's port. There is no handshake or preface.
- The client sends one REQUEST and then reads frames until the response ends (§4).
  Only then may it send the next REQUEST. Requests are never interleaved.
- The server **keeps the connection open** after each response and waits for the next
  request. It closes the connection only when the peer closes it, when a frame header or
  payload is cut short by EOF, or after answering a request that carried `connection: close`.
- A client **never opens a second connection**. It sends all its requests over one connection.
- All integers are unsigned and big-endian (network byte order). All text is UTF-8.

## 2. Frame header (5 bytes, fixed)

```
 0                   1                   2                   3
+-------+-------+-------+-------+-------+----------- ... --------+
|      Length (24)      | Type  | Flags |   Payload (Length bytes)
+-------+-------+-------+-------+-------+----------- ... --------+
```

| Field  | Bits | Meaning |
|--------|------|---------|
| Length | 24   | Payload length in bytes, **not** counting this 5-byte header (0 – 16 777 215). |
| Type   | 8    | Frame type (§3). |
| Flags  | 8    | Bit 0 (`0x01`) = **END**. Senders MUST set the other bits to 0. Receivers MUST ignore them. |

**Why these widths.** HTTP/2 uses 24/8/8/31 (9 bytes). We keep its first three fields and
drop the 31-bit stream ID.
- **Length = 24 bits.** 16 bits (64 KiB max) would cap one header block or one
  REQUEST too tightly. 32 bits would spend a byte on every frame for sizes we never want
  in a single frame. 24 bits allows up to 16 MiB. Our senders still split bodies into
  DATA frames of at most 16 384 bytes, so a receiver only ever needs a small buffer.
  This is the same reasoning HTTP/2 uses.
- **Type = 8 bits.** We use 3 values. The other 253 are room for v2. Together with the
  skip rule in §6, this is how the protocol grows.
- **Flags = 8 bits.** We need only END today. A whole byte keeps the header byte-aligned
  and leaves 7 bits spare.
- **No stream ID.** HTTP/2 needs 31 bits to multiplex many streams on one connection.
  BHTTP/1 allows one outstanding request per connection, so the "stream" is implicit and
  responses come back in order. A stream ID would cost 4 bytes per frame and buy nothing.
  If v2 adds multiplexing, it does so with a new frame type (§6).

Because the length always comes first, a receiver can find where the next frame starts
even when it cannot parse the current payload. A bad payload therefore does not
desynchronise the connection, and the server can answer 400 and carry on.

## 3. Frame types

| Type   | Name     | Direction | Payload |
|--------|----------|-----------|---------|
| `0x01` | REQUEST  | C → S | `Method(1)` `PathLen(2)` `Path(PathLen)` `HeaderBlock(rest)` |
| `0x02` | RESPONSE | S → C | `Status(2)` `HeaderBlock(rest)` |
| `0x03` | DATA     | S → C | Raw body bytes. |
| other  | —        | any   | Unknown: MUST be skipped (§6). |

- **Method:** `0x01` = GET, `0x02` = HEAD. Any other value → 405.
- **Path:** must start with `/` and must not contain NUL. Everything after `?` is ignored.
  No percent-encoding is needed because the path is length-prefixed.
- **Status:** an HTTP status code, e.g. 200 = `00 C8`.
- The header block runs to the end of the payload (§5). There is no count field.

## 4. Message exchange

**Request.** One REQUEST frame. Flags are 0. BHTTP/1 requests have no body.

**Response.** One RESPONSE frame, then the body:
- If the body is empty, or the method was HEAD, the RESPONSE has **END** set and no DATA follows.
- Otherwise the RESPONSE has flags 0, and one or more DATA frames follow. The **last** DATA
  frame has END set. The body is the concatenation of the DATA payloads, and its total size
  equals `content-length`.

The client knows a response is complete when it sees END. Unknown frames between these
frames are skipped (§6).

## 5. Header block

The header block is a sequence of entries with no separators:

```
indexed:  [Index 1..10 (1)] [ValueLen (2)] [Value]
literal:  [0x00 (1)] [NameLen (1)] [Name] [ValueLen (2)] [Value]
```

These are HPACK's first two mechanisms: a **static table** of the names we actually send,
and **length-prefixing** for everything else. Names are lowercase ASCII, 1–255 bytes.
Values are 0–65 535 bytes of UTF-8. A sender MUST use the index when the name is in the table.

| # | Name | Sent by | | # | Name | Sent by |
|---|------|---------|-|---|------|---------|
| 1 | host | client | | 6 | date | server |
| 2 | user-agent | client | | 7 | content-type | server |
| 3 | accept | client | | 8 | content-length | server |
| 4 | connection | both | | 9 | last-modified | server |
| 5 | server | server | | 10 | etag | server |

- `connection: close` from a client means: answer this request, then close.
  The server echoes `connection: close` in that response.
- An index from 11 to 255 is unknown in v1. The receiver reads past its value using
  ValueLen and ignores that header. This leaves room for a bigger table in v2.
- A block is **malformed** if any length runs past the end of the payload, if NameLen is 0,
  or if a name or value is not valid ASCII or UTF-8 respectively.

## 6. Extensibility rule (MUST)

> A receiver that meets a frame Type it does not know **MUST** read and discard exactly
> `Length` payload bytes and continue with the next frame. It MUST NOT treat the frame as
> an error and MUST NOT close the connection because of it.

This is how a v2 sender can add frames (settings, multiplexing, trailers, request bodies)
without breaking v1 peers. A v1 peer simply ignores them.

## 7. Server behaviour and errors

`bserve ROOT PORT` maps the request path onto a file under `ROOT`:
- A path ending in `/` gets `index.html` appended.
- The result is resolved to a real path and must stay inside `ROOT`, so `../` escapes are blocked.

| Status | When | Body |
|--------|------|------|
| 200 | The file exists. | File bytes, with `content-type`, `content-length`, `last-modified` and `etag`. |
| 400 | The REQUEST payload is malformed (§3, §5), its payload is larger than 64 KiB, or the client sent a RESPONSE or DATA frame. | Short text explaining why. |
| 404 | No such file, or the path escapes ROOT. | `404 Not Found` |
| 405 | Unknown method byte. | Short text. |
| 500 | The file exists but cannot be read. | Short text. |

After a 400, the server **keeps the connection open**: the frame length was valid, so the
next frame boundary is known. Every response carries `server`, `date` and `content-length`.

## 8. Client behaviour

`bcurl [-v] [-I] [-H 'name: value'] HOST:PORT/PATH ...` works as follows:
- It sends `host`, `user-agent` and `accept` with every request, and `connection: close`
  with the last one.
- It writes the body to stdout.
- `-v` hexdumps every frame to stderr: `>` for frames sent, `<` for frames received.
- All URLs must share one host:port and are fetched over **one** connection.
- Exit status is 0 if every response was below 400, 1 if any response was 4xx/5xx, and
  2 for a usage, network or protocol error.
