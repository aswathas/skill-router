#!/usr/bin/env python3
"""Semantic layer for the router: embed the catalogue, cache it, query it.

The keyword matcher only fires when a request shares a literal string with a
capability's keyword list. The benchmark showed that is where most of the
loss is: 42 of 45 failures were requests that never named the capability.
An embedding index closes that gap without a model in the loop at request
time - the catalogue is embedded once, and a request is embedded once.

The embedding provider is a local LM Studio server with an OpenAI-compatible
endpoint. Nothing leaves the machine.

    python embed.py build                 # embed the catalogue and the capabilities
    python embed.py query "make it fast"  # ten nearest skills
    python embed.py status                # what is cached

Environment:
    EMBED_BASE_URL  default http://127.0.0.1:1234/v1
    EMBED_MODEL     default text-embedding-nomic-embed-text-v1.5
    EMBED_API_KEY   optional bearer token
"""

import array
import base64
import hashlib
import json
import math
import os
import sys
import urllib.request
from pathlib import Path

STATE_ENV = "SKILL_ROUTER_STATE_DIR"
DEFAULT_STATE = Path.home() / ".minimax" / "local-runtime" / "skill-learning"
BASE_URL = os.environ.get("EMBED_BASE_URL", "http://127.0.0.1:1234/v1").rstrip("/")
MODEL = os.environ.get("EMBED_MODEL", "text-embedding-nomic-embed-text-v1.5")
CACHE_NAME = "embeddings.json"
BATCH = 64
MAX_TEXT = 600
_CACHE = {}


def state_dir():
    env = os.environ.get(STATE_ENV)
    return Path(env) if env else DEFAULT_STATE


def cache_path():
    return state_dir() / CACHE_NAME


def _key(text):
    return hashlib.sha1(text.encode("utf-8", "ignore")).hexdigest()


def load_cache():
    """Read the vector cache. The file is big, so it is parsed once."""
    p = cache_path()
    try:
        stamp = p.stat().st_mtime
    except OSError:
        return {"model": MODEL, "dim": 0, "texts": {}, "keys": {}}
    if _CACHE.get("stamp") == stamp:
        return _CACHE["data"]
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"model": MODEL, "dim": 0, "texts": {}, "keys": {}}
    data.setdefault("texts", {})
    data.setdefault("keys", {})
    _CACHE["stamp"] = stamp
    _CACHE["data"] = data
    return data


def save_cache(cache):
    p = cache_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    packed = {"model": cache.get("model"), "dim": cache.get("dim"),
              "keys": cache.get("keys", {}),
              "texts": {h: (_pack(v) if isinstance(v, (list, array.array)) else v)
                        for h, v in cache.get("texts", {}).items()}}
    p.write_text(json.dumps(packed, ensure_ascii=False), encoding="utf-8")
    cache["texts"] = packed["texts"]
    _CACHE["stamp"] = p.stat().st_mtime
    _CACHE["data"] = cache


def _post(texts):
    payload = {"model": MODEL, "input": texts}
    req = urllib.request.Request(
        BASE_URL + "/embeddings",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"})
    key = os.environ.get("EMBED_API_KEY")
    if key:
        req.add_header("Authorization", "Bearer " + key)
    with urllib.request.urlopen(req, timeout=120) as resp:
        data = json.load(resp)
    items = sorted(data["data"], key=lambda d: d.get("index", 0))
    return [d["embedding"] for d in items]


def embed_texts(texts, cache=None, progress=False):
    """Embed a list of strings, using the cache and writing what is new."""
    cache = cache if cache is not None else load_cache()
    texts = [t[:MAX_TEXT] for t in texts]
    out = [None] * len(texts)
    todo, todo_idx = [], []
    for i, t in enumerate(texts):
        k = _key(t)
        if k in cache["texts"]:
            out[i] = _vec(cache, k)
        else:
            todo.append(t)
            todo_idx.append(i)
    for i in range(0, len(todo), BATCH):
        chunk = todo[i:i + BATCH]
        vecs = _post(chunk)
        for t, v in zip(chunk, vecs):
            cache["texts"][_key(t)] = v
        for idx, v in zip(todo_idx[i:i + BATCH], vecs):
            out[idx] = v
        if progress:
            print("  embedded %d/%d" % (min(i + BATCH, len(todo)), len(todo)), flush=True)
    if cache["dim"] == 0 and out and out[0]:
        cache["dim"] = len(out[0])
    return out, cache


def cosine(a, b):
    if not a or not b:
        return 0.0
    num = 0.0
    da = 0.0
    db = 0.0
    for x, y in zip(a, b):
        num += x * y
        da += x * x
        db += y * y
    if da == 0 or db == 0:
        return 0.0
    return num / math.sqrt(da * db)


# Vectors are stored as base64 float32. As plain JSON floats the cache for
# 3,000 skills was 101 MB and took a second to parse; packed, it is a fifth
# of that and loads in a fraction of it.
def _pack(vec):
    return base64.b64encode(array.array("f", vec).tobytes()).decode("ascii")


def _unpack(blob):
    a = array.array("f")
    a.frombytes(base64.b64decode(blob))
    return a


def _vec(cache, h):
    v = cache["texts"].get(h)
    if v is None:
        return None
    if isinstance(v, str):
        v = _unpack(v)
        cache["texts"][h] = v
    elif not isinstance(v, array.array):
        v = array.array("f", v)
        cache["texts"][h] = v
    return v


def registry_skills(reg):
    return list(reg.get("local") or []) + list(reg.get("plugin") or []) + \
        list(reg.get("marketplace") or [])


def skill_text(s):
    return "%s %s %s" % (s.get("name") or "", s.get("slug") or "",
                         (s.get("description") or "")[:MAX_TEXT])


def build(reg, cap_map):
    """Embed every skill, then the centroid of every capability."""
    cache = load_cache()
    skills = registry_skills(reg)
    seen = set()
    uniq = []
    for s in skills:
        slug = s.get("slug") or s.get("name")
        if not slug or slug in seen:
            continue
        seen.add(slug)
        uniq.append(s)
    texts = [skill_text(s) for s in uniq]
    print("embedding %d skills" % len(texts))
    vecs, cache = embed_texts(texts, cache, progress=True)
    for s, v in zip(uniq, vecs):
        cache["keys"]["s:" + (s.get("slug") or s.get("name"))] = _key(skill_text(s))
    # A capability is what its skills are about, so it is represented by the
    # mean of their vectors. That is far richer than its keyword list.
    sums = {}
    counts = {}
    for s, v in zip(uniq, vecs):
        for cap in s.get("tags") or []:
            acc = sums.setdefault(cap, [0.0] * len(v))
            for i, x in enumerate(v):
                acc[i] += x
            counts[cap] = counts.get(cap, 0) + 1
    for cap, acc in sums.items():
        n = counts[cap]
        centroid = [x / n for x in acc]
        cache["keys"]["c:" + cap] = _key("cap:" + cap)
        cache["texts"][_key("cap:" + cap)] = centroid
    cache["model"] = MODEL
    cache["dim"] = len(vecs[0]) if vecs and vecs[0] else 0
    save_cache(cache)
    print("skills %d, capabilities %d, dim %d" % (len(uniq), len(sums), cache["dim"]))
    return cache


def skill_vectors(cache):
    """{slug: vector} for every embedded skill."""
    out = {}
    for key, h in (cache.get("keys") or {}).items():
        if key.startswith("s:"):
            v = _vec(cache, h)
            if v is not None:
                out[key[2:]] = v
    return out


def capability_vectors(cache):
    out = {}
    for key, h in (cache.get("keys") or {}).items():
        if key.startswith("c:"):
            v = _vec(cache, h)
            if v is not None:
                out[key[2:]] = v
    return out


def query(text, reg, cache=None, top=10):
    cache = cache if cache is not None else load_cache()
    vecs, cache = embed_texts([text], cache)
    q = vecs[0]
    sv = skill_vectors(cache)
    scored = []
    for slug, v in sv.items():
        if v:
            scored.append((cosine(q, v), slug))
    scored.sort(reverse=True)
    by_slug = {s.get("slug"): s for s in registry_skills(reg)}
    return [(round(c, 4), by_slug.get(slug, {}).get("name") or slug) for c, slug in scored[:top]]


def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("build")
    sub.add_parser("status")
    p = sub.add_parser("query")
    p.add_argument("text")
    p.add_argument("--top", type=int, default=10)
    args = ap.parse_args(argv)

    if args.cmd == "build":
        reg = json.loads((state_dir() / "skills.json").read_text(encoding="utf-8"))
        caps = json.loads((state_dir() / "capabilities.json").read_text(encoding="utf-8"))
        build(reg, caps.get("capabilities", {}))
        return 0
    if args.cmd == "status":
        cache = load_cache()
        sv = skill_vectors(cache)
        cv = capability_vectors(cache)
        print("model      : %s" % cache.get("model"))
        print("dim        : %s" % cache.get("dim"))
        print("skills     : %d" % len(sv))
        print("capabilities: %d" % len(cv))
        print("cache      : %s" % cache_path())
        return 0
    reg = json.loads((state_dir() / "skills.json").read_text(encoding="utf-8"))
    for c, name in query(args.text, reg, top=args.top):
        print("%.4f  %s" % (c, name))
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
