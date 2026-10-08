# Annotated hexdump — one complete request and response

**Arjun · Roll No. 24bcs10109**

Captured with `./bcurl -v localhost:9100/index.html` against `./bserve ./www 9100`.
(Port 9100 was used because 9000 was already taken on the test machine. The port only
changes the `host` value.) `www/index.html` is 182 bytes. Offsets are from the start of
each frame.

## Request: client → server (5 + 57 = 62 bytes)

```
> 0000  00 00 39 01 00 01 00 0b 2f 69 6e 64 65 78 2e 68  |..9...../index.h|
> 0010  74 6d 6c 01 00 0e 6c 6f 63 61 6c 68 6f 73 74 3a  |tml...localhost:|
> 0020  39 31 30 30 02 00 09 62 63 75 72 6c 2f 31 2e 30  |9100...bcurl/1.0|
> 0030  03 00 03 2a 2f 2a 04 00 05 63 6c 6f 73 65        |...*/*...close|
```

| Offset | Bytes | Meaning |
|--------|-------|---------|
| 00–02 | `00 00 39` | **Length** = 57 payload bytes |
| 03 | `01` | **Type** = REQUEST |
| 04 | `00` | **Flags** = none |
| 05 | `01` | Method = GET |
| 06–07 | `00 0b` | PathLen = 11 |
| 08–12 | `2f 69 … 6c` | Path = `/index.html` |
| 13 | `01` | Header index 1 = `host` |
| 14–15 | `00 0e` | ValueLen = 14 |
| 16–23 | `6c 6f … 30` | `localhost:9100` |
| 24 | `02` | Header index 2 = `user-agent` |
| 25–26 | `00 09` | ValueLen = 9 |
| 27–2f | `62 63 … 30` | `bcurl/1.0` |
| 30 | `03` | Header index 3 = `accept` |
| 31–32 | `00 03` | ValueLen = 3 |
| 33–35 | `2a 2f 2a` | `*/*` |
| 36 | `04` | Header index 4 = `connection` |
| 37–38 | `00 05` | ValueLen = 5 |
| 39–3d | `63 6c 6f 73 65` | `close` (last request, so the server may close after replying) |

Check: 1 + 2 + 11 + (3+14) + (3+9) + (3+3) + (3+5) = **57**. ✔

## Response frame 1: RESPONSE, server → client (5 + 121 = 126 bytes)

```
< 0000  00 00 79 02 00 00 c8 05 00 0a 62 73 65 72 76 65  |..y.......bserve|
< 0010  2f 31 2e 30 06 00 1d 54 68 75 2c 20 30 38 20 4f  |/1.0...Thu, 08 O|
< 0020  63 74 20 32 30 32 36 20 31 35 3a 33 30 3a 30 38  |ct 2026 15:30:08|
< 0030  20 47 4d 54 08 00 03 31 38 32 07 00 09 74 65 78  | GMT...182...tex|
< 0040  74 2f 68 74 6d 6c 09 00 1d 54 68 75 2c 20 30 38  |t/html...Thu, 08|
< 0050  20 4f 63 74 20 32 30 32 36 20 31 35 3a 33 30 3a  | Oct 2026 15:30:|
< 0060  30 32 20 47 4d 54 0a 00 0d 22 62 36 2d 36 61 63  |02 GMT..."b6-6ac|
< 0070  37 62 36 66 61 22 04 00 05 63 6c 6f 73 65        |7b6fa"...close|
```

| Offset | Bytes | Meaning |
|--------|-------|---------|
| 00–02 | `00 00 79` | **Length** = 121 |
| 03 | `02` | **Type** = RESPONSE |
| 04 | `00` | **Flags** = 0, so the body follows in DATA frames |
| 05–06 | `00 c8` | Status = **200** |
| 07 | `05` | Index 5 = `server` |
| 08–09 | `00 0a` | ValueLen = 10 |
| 0a–13 | | `bserve/1.0` |
| 14 | `06` | Index 6 = `date` |
| 15–16 | `00 1d` | ValueLen = 29 |
| 17–33 | | `Thu, 08 Oct 2026 15:30:08 GMT` |
| 34 | `08` | Index 8 = `content-length` |
| 35–36 | `00 03` | ValueLen = 3 |
| 37–39 | `31 38 32` | `182` |
| 3a | `07` | Index 7 = `content-type` |
| 3b–3c | `00 09` | ValueLen = 9 |
| 3d–45 | | `text/html` |
| 46 | `09` | Index 9 = `last-modified` |
| 47–48 | `00 1d` | ValueLen = 29 |
| 49–65 | | `Thu, 08 Oct 2026 15:30:02 GMT` |
| 66 | `0a` | Index 10 = `etag` |
| 67–68 | `00 0d` | ValueLen = 13 |
| 69–75 | | `"b6-6ac7b6fa"` (size 0xb6 = 182, mtime in hex) |
| 76 | `04` | Index 4 = `connection` |
| 77–78 | `00 05` | ValueLen = 5 |
| 79–7d | | `close` (echoed: the server closes after this response) |

Check: 2 + (3+10) + (3+29) + (3+3) + (3+9) + (3+29) + (3+13) + (3+5) = **121**. ✔
Every header name above costs **1 byte** instead of the 4–14 bytes it takes in HTTP/1.1.

## Response frame 2: DATA, server → client (5 + 182 = 187 bytes)

```
< 0000  00 00 b6 03 01 3c 21 64 6f 63 74 79 70 65 20 68  |.....<!doctype h|
< 0010  74 6d 6c 3e 0a 3c 68 74 6d 6c 20 6c 61 6e 67 3d  |tml>.<html lang=|
< 0020  22 65 6e 22 3e 0a 3c 6d 65 74 61 20 63 68 61 72  |"en">.<meta char|
< 0030  73 65 74 3d 22 75 74 66 2d 38 22 3e 0a 3c 74 69  |set="utf-8">.<ti|
< 0040  74 6c 65 3e 42 69 6e 61 72 79 20 48 54 54 50 20  |tle>Binary HTTP |
< 0050  63 6f 75 72 73 65 20 70 72 6f 6a 65 63 74 3c 2f  |course project</|
< 0060  74 69 74 6c 65 3e 0a 3c 68 31 3e 42 69 6e 61 72  |title>.<h1>Binar|
< 0070  79 20 48 54 54 50 20 77 6f 72 6b 73 3c 2f 68 31  |y HTTP works</h1|
< 0080  3e 0a 3c 70 3e 41 72 6a 75 6e 20 7c 20 32 34 42  |>.<p>Arjun | 24B|
< 0090  43 53 31 30 31 30 39 20 7c 20 4e 65 74 77 6f 72  |CS10109 | Networ|
< 00a0  6b 20 41 72 63 68 69 74 65 63 74 75 72 65 3c 2f  |k Architecture</|
< 00b0  70 3e 0a 3c 2f 68 74 6d 6c 3e 0a                 |p>.</html>.|
```

| Offset | Bytes | Meaning |
|--------|-------|---------|
| 00–02 | `00 00 b6` | **Length** = 182 |
| 03 | `03` | **Type** = DATA |
| 04 | `01` | **Flags** = END, the last frame of this response |
| 05–ba | `3c 21 … 0a` | The 182-byte body of `index.html`, matching `content-length` |

The body is smaller than the 16 384-byte DATA limit, so it fits in one frame. END is set,
so the response is complete. Because the request said `connection: close`, the server
closes the TCP connection. Without that header it would have waited for the next REQUEST.
