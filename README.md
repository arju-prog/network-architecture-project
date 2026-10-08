# BHTTP/1 — Arjun (24bcs10109)

Python 3, standard library only.

| File | What it is |
|------|------------|
| `SPEC.md` | The protocol spec (hand-in 1) |
| `bserve.py`, `bcurl.py` | The server and the client (hand-in 2) |
| `HEXDUMP.md` | Annotated hexdump of one request and response (hand-in 3) |
| `test.py` | Raw-byte tests: 400 on a malformed frame, unknown frames skipped, connection kept open |
| `www/` | Sample files to serve |

```sh
./bserve.py ./www 9000                         # terminal 1
./bcurl.py -v localhost:9000/index.html        # terminal 2: hexdump every frame
./bcurl.py localhost:9000/ localhost:9000/style.css   # 2 requests, 1 connection
./bcurl.py localhost:9000/missing; echo $?     # 404 -> exit 1
./test.py 9000
```
