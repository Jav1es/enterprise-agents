"""极简内存版 Redis（仅实现压测用到的命令），零依赖、纯标准库。

为什么需要它：本机没有 Redis，Docker 也未运行，导致编排链路里
ShortTermMemory 每请求都连接超时 + 重试 —— 多 worker 下成正反馈雪崩
（见 bench/ARCH_BOTTLENECK.md）。要测「记忆路径正常时」的真实容量，
必须先让 Redis 可达。

为什么不用装 redis / fakeredis：
- 装 redis 需要管理员 + 服务注册，且是常驻服务，测完还要清理
- fakeredis 是库不是服务，改不了应用的 redis.asyncio 连接目标
- 本脚本只做「让连接成功」，不追求 Redis 语义完备

支持的命令（够 ShortTermMemory 用）：
  PING / ECHO / SET / GET / DEL / EXISTS / EXPIRE / TTL / INCR / DBSIZE / FLUSHALL / QUIT / SELECT
  + HSET / HGET / HGETALL / HDEL（List 存取若用到）

⚠️ 单线程 accept 循环，只为压测；不要用于生产。
用法：
    python bench/mini_redis.py --port 6379
"""

from __future__ import annotations

import argparse
import socket
import threading
import time
from typing import Any

_store: dict[str, Any] = {}
_expiry: dict[str, float] = {}
_lock = threading.Lock()


def _expired(key: str) -> bool:
    exp = _expiry.get(key)
    return exp is not None and exp < time.time()


def _get(key: str) -> Any:
    if _expired(key):
        _store.pop(key, None)
        _expiry.pop(key, None)
        return None
    return _store.get(key)


def cmd_get(args: list[bytes]) -> Any:
    return _get(args[0].decode())


def cmd_set(args: list[bytes]) -> Any:
    key, val = args[0].decode(), args[1]
    with _lock:
        _store[key] = val
        _expiry.pop(key, None)
    # SET key val EX n
    if len(args) >= 4 and args[2].upper() == b"EX":
        _expiry[key] = time.time() + int(args[3])
    return b"OK"


def cmd_del(args: list[bytes]) -> Any:
    n = 0
    with _lock:
        for a in args:
            k = a.decode()
            if k in _store:
                n += 1
            _store.pop(k, None)
            _expiry.pop(k, None)
    return n


def cmd_exists(args: list[bytes]) -> Any:
    return sum(1 for a in args if _get(a.decode()) is not None)


def cmd_expire(args: list[bytes]) -> Any:
    key, sec = args[0].decode(), int(args[1])
    if _get(key) is None:
        return 0
    _expiry[key] = time.time() + sec
    return 1


def cmd_ttl(args: list[bytes]) -> Any:
    key = args[0].decode()
    if _get(key) is None:
        return -2
    exp = _expiry.get(key)
    return -1 if exp is None else max(0, int(exp - time.time()))


def cmd_incr(args: list[bytes]) -> Any:
    key = args[0].decode()
    with _lock:
        cur = int(_store.get(key, b"0")) + 1
        _store[key] = str(cur).encode()
    return cur


def cmd_hset(args: list[bytes]) -> Any:
    key = args[0].decode()
    cur = _store.get(key)
    if not isinstance(cur, dict):
        cur = {}
        _store[key] = cur
    n = 0
    for i in range(2, len(args) - 1, 2):
        if args[i].decode() not in cur:
            n += 1
        cur[args[i].decode()] = args[i + 1]
    return n


def cmd_hget(args: list[bytes]) -> Any:
    cur = _get(args[0].decode())
    if not isinstance(cur, dict):
        return None
    return cur.get(args[1].decode())


def cmd_hgetall(args: list[bytes]) -> Any:
    cur = _get(args[0].decode())
    return cur if isinstance(cur, dict) else {}


def cmd_hdel(args: list[bytes]) -> Any:
    cur = _get(args[0].decode())
    if not isinstance(cur, dict):
        return 0
    n = sum(1 for a in args[1:] if cur.pop(a.decode(), None) is not None)
    return n


def cmd_flushall(_args: list[bytes]) -> Any:
    _store.clear()
    _expiry.clear()
    return b"OK"


def cmd_dbsize(_args: list[bytes]) -> Any:
    return len([k for k in _store if not _expired(k)])


def encode(v: Any) -> bytes:
    if v is None:
        return b"$-1\r\n"
    if isinstance(v, bool):
        return b":1\r\n" if v else b":0\r\n"
    if isinstance(v, int):
        return f":{v}\r\n".encode()
    if isinstance(v, bytes):
        return b"$" + str(len(v)).encode() + b"\r\n" + v + b"\r\n"
    if isinstance(v, str):
        b = v.encode()
        return b"$" + str(len(b)).encode() + b"\r\n" + b + b"\r\n"
    if isinstance(v, Resp3Map):  # RESP3 map → %N
        n = len(v) * 2
        return b"%" + str(n).encode() + b"\r\n" + b"".join(
            encode(k) + encode(val) for k, val in v.items())
    if isinstance(v, dict):  # HGETALL → RESP2 flat array
        flat: list[bytes] = []
        for k, val in v.items():
            flat.append(k.encode() if isinstance(k, str) else k)
            flat.append(val if isinstance(val, bytes) else str(val).encode())
        return b"*" + str(len(flat)).encode() + b"\r\n" + b"".join(
            encode(x) for x in flat)
    if isinstance(v, (list, tuple)):
        return b"*" + str(len(v)).encode() + b"\r\n" + b"".join(encode(x) for x in v)
    return encode(str(v))


class Resp3Map(dict):
    """标记类：告诉 encode() 用 RESP3 的 %N 格式编码（RESP2 用 *N）。"""


def cmd_hello(args: list[bytes]) -> Any:
    """RESP3 / RESP2 握手。

    ⚠️ redis-py 8.x 默认 protocol=3，连上就发 HELLO；不实现它，
    客户端会卡在等握手响应直到超时（实测踩过：redis.exceptions.TimeoutError）。
    HELLO 2 时按 RESP2 数组回，HELLO 3 / 无参按 RESP3 map 回。
    """
    proto = args[0].decode() if args else "3"
    fields = {
        "server": "mini-redis", "version": "7.0.0-mini", "id": 1,
        "mode": "standalone", "role": "master",
    }
    if proto == "2":
        flat: list[bytes] = []
        for k, v in fields.items():
            flat.append(k.encode())
            flat.append(v.encode())
        return flat
    return Resp3Map(fields)


HANDLERS = {
    b"HELLO": cmd_hello,
    b"PING": lambda a: b"PONG" if not a else a[0],
    b"ECHO": lambda a: a[0],
    b"GET": cmd_get, b"SET": cmd_set, b"DEL": cmd_del, b"UNLINK": cmd_del,
    b"EXISTS": cmd_exists, b"EXPIRE": cmd_expire, b"TTL": cmd_ttl, b"PTTL": cmd_ttl,
    b"INCR": cmd_incr, b"INCRBY": lambda a: int(a[1]) + int(_store.get(a[0].decode(), b"0")),
    b"HSET": cmd_hset, b"HGET": cmd_hget, b"HGETALL": cmd_hgetall, b"HDEL": cmd_hdel,
    b"FLUSHALL": cmd_flushall, b"FLUSHDB": cmd_flushall,
    b"DBSIZE": cmd_dbsize,
    b"SELECT": lambda a: b"OK", b"QUIT": lambda a: b"OK",
    b"CLIENT": lambda a: b"OK", b"CONFIG": lambda a: b"OK",
    b"INFO": lambda a: b"# Server\r\nredis_version:mini\r\n",
}


def handle(conn: socket.socket) -> None:
    conn.settimeout(120)
    buf = b""
    try:
        while True:
            data = conn.recv(65536)
            if not data:
                return
            buf += data
            # RESP 数组格式： *N\r\n$len\r\n<arg>\r$n...
            while True:
                if not buf.startswith(b"*"):
                    # 内联命令
                    if b"\r\n" in buf:
                        line, buf = buf.split(b"\r\n", 1)
                        parts = line.split()
                        if parts:
                            conn.sendall(encode(HANDLERS.get(parts[0].upper(), lambda _a: None)(parts[1:])))
                        continue
                    break
                nl = buf.find(b"\r\n")
                if nl == -1:
                    break
                n = int(buf[1:nl])
                pos = nl + 2
                args: list[bytes] = []
                ok = True
                for _ in range(n):
                    if pos >= len(buf) or buf[pos:pos + 1] != b"$":
                        ok = False
                        break
                    e = buf.find(b"\r\n", pos)
                    if e == -1:
                        ok = False
                        break
                    ln = int(buf[pos + 1:e])
                    start = e + 2
                    if len(buf) < start + ln + 2:
                        ok = False
                        break
                    args.append(buf[start:start + ln])
                    pos = start + ln + 2
                if not ok:
                    break
                buf = buf[pos:]
                name = args[0].upper() if args else b""
                fn = HANDLERS.get(name)
                conn.sendall(encode(fn(args[1:]) if fn else None))
    except Exception:
        pass
    finally:
        try:
            conn.close()
        except Exception:
            pass


def main() -> None:
    ap = argparse.ArgumentParser(description="极简内存版 Redis（压测专用）")
    ap.add_argument("--port", type=int, default=6379)
    ap.add_argument("--host", default="127.0.0.1")
    args = ap.parse_args()
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind((args.host, args.port))
    s.listen(128)
    print(f"mini-redis 监听 {args.host}:{args.port}（Ctrl+C 停止）", flush=True)
    try:
        while True:
            conn, _ = s.accept()
            threading.Thread(target=handle, args=(conn,), daemon=True).start()
    except KeyboardInterrupt:
        print("\n已停止")


if __name__ == "__main__":
    main()
