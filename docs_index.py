"""Pencarian dokumentasi Markdown untuk Jarvis (SQLite FTS5, tanpa library tambahan).

Cara kerja singkat:
  1. sync()   : memindai folder dokumentasi, mengindeks file .md yang baru/berubah,
                dan membuang file yang sudah dihapus. Murah, aman dipanggil berulang.
  2. search() : mencari bagian (chunk) yang paling relevan dengan pertanyaan.
"""
import os
import re
import sqlite3

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.environ.get("JARVIS_DB", os.path.join(BASE_DIR, ".jarvis_docs.db"))

MAX_CHUNK_CHARS = 1200  # batas ukuran satu potongan dokumen

STOPWORDS = set(
    """
yang dan di ke dari untuk pada dengan adalah itu ini atau apa siapa kapan dimana
bagaimana gimana kenapa mengapa saya aku kamu kita kalo kalau bisa tidak ga gak
nggak ada akan sudah sedang juga ya dong sih deh cara tolong jelaskan
the an of to in on for is are was were be do does how what why when where who which
can you we it my me and or with this that tell about please
""".split()
)

HEADING_RE = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")
FRONT_MATTER_RE = re.compile(r"\A---\s*\n.*?\n---\s*\n", re.DOTALL)


# ------------------------------------------------------------------ Database
def connect(db_path=None):
    conn = sqlite3.connect(db_path or DB_PATH)
    try:
        conn.execute(
            "CREATE VIRTUAL TABLE IF NOT EXISTS chunks USING fts5("
            "path UNINDEXED, heading, body, "
            "tokenize = 'porter unicode61 remove_diacritics 2')"
        )
    except sqlite3.OperationalError as e:
        raise RuntimeError("SQLite di Python ini tidak mendukung FTS5") from e
    conn.execute(
        "CREATE TABLE IF NOT EXISTS files "
        "(path TEXT PRIMARY KEY, mtime REAL, size INTEGER)"
    )
    return conn


# ------------------------------------------------------------------ Chunking
def _split_long(body, limit=MAX_CHUNK_CHARS):
    """Pecah teks panjang per paragraf supaya tiap potongan tidak terlalu besar."""
    if len(body) <= limit:
        return [body]
    parts, buf = [], ""
    for para in re.split(r"\n\s*\n", body):
        if buf and len(buf) + len(para) + 2 > limit:
            parts.append(buf)
            buf = para
        else:
            buf = f"{buf}\n\n{para}" if buf else para
    if buf:
        parts.append(buf)
    out = []
    for p in parts:  # satu paragraf/blok kode yang sangat panjang: potong paksa
        while len(p) > limit * 2:
            out.append(p[:limit])
            p = p[limit:]
        out.append(p)
    return out


def _emit(sections, heading, lines):
    body = "\n".join(lines).strip()
    if body:
        sections.append((heading, body))


def chunk_markdown(text, doc_title):
    """Pecah Markdown per heading. Hasil: list of (breadcrumb_heading, body)."""
    text = FRONT_MATTER_RE.sub("", text, count=1)
    sections, stack, lines = [], [], []
    heading, in_code = doc_title, False

    for line in text.splitlines():
        stripped = line.lstrip()
        if stripped.startswith("```") or stripped.startswith("~~~"):
            in_code = not in_code
            lines.append(line)
            continue
        m = None if in_code else HEADING_RE.match(line)
        if m:
            _emit(sections, heading, lines)
            lines = []
            level, title = len(m.group(1)), m.group(2)
            while stack and stack[-1][0] >= level:
                stack.pop()
            stack.append((level, title))
            heading = " › ".join(t for _, t in stack)
        else:
            lines.append(line)
    _emit(sections, heading, lines)

    chunks = []
    for head, body in sections:
        for piece in _split_long(body):
            chunks.append((head, piece))
    return chunks


# ------------------------------------------------------------------ Indexing
def _delete_file(conn, rel):
    conn.execute("DELETE FROM chunks WHERE path = ?", (rel,))
    conn.execute("DELETE FROM files WHERE path = ?", (rel,))


def _index_file(conn, rel, full, mtime, size):
    _delete_file(conn, rel)
    with open(full, encoding="utf-8", errors="replace") as f:
        text = f.read()
    title = os.path.splitext(os.path.basename(rel))[0].replace("-", " ").replace("_", " ")
    for head, body in chunk_markdown(text, title):
        conn.execute(
            "INSERT INTO chunks (path, heading, body) VALUES (?, ?, ?)", (rel, head, body)
        )
    conn.execute(
        "INSERT INTO files (path, mtime, size) VALUES (?, ?, ?)", (rel, mtime, size)
    )


def sync(docs_dir, conn):
    """Samakan indeks dengan isi folder. Return (ditambah, diubah, dihapus)."""
    found = {}
    if os.path.isdir(docs_dir):
        for root, dirs, files in os.walk(docs_dir):
            dirs[:] = [d for d in dirs if not d.startswith(".") and d != "node_modules"]
            for name in files:
                if name.lower().endswith(".md"):
                    full = os.path.join(root, name)
                    st = os.stat(full)
                    found[os.path.relpath(full, docs_dir)] = (full, st.st_mtime, st.st_size)

    known = {p: (m, s) for p, m, s in conn.execute("SELECT path, mtime, size FROM files")}
    added = updated = removed = 0

    for rel, (full, mtime, size) in found.items():
        if rel in known:
            if known[rel] == (mtime, size):
                continue
            updated += 1
        else:
            added += 1
        _index_file(conn, rel, full, mtime, size)

    for rel in set(known) - set(found):
        _delete_file(conn, rel)
        removed += 1

    conn.commit()
    return added, updated, removed


def stats(conn):
    """Return (jumlah_file, jumlah_potongan)."""
    n_files = conn.execute("SELECT COUNT(*) FROM files").fetchone()[0]
    n_chunks = conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
    return n_files, n_chunks


# ------------------------------------------------------------------ Search
def _terms(query):
    words = re.findall(r"\w+", query.lower())
    return [w for w in dict.fromkeys(words) if len(w) > 2 and w not in STOPWORDS]


def search(conn, query, k=3):
    """Cari potongan dokumentasi paling relevan. Return list of dict (bisa kosong)."""
    terms = _terms(query)
    if not terms:
        return []
    match = " OR ".join(f'"{t}"' for t in terms)
    rows = conn.execute(
        "SELECT path, heading, body, bm25(chunks, 0.0, 4.0, 1.0) AS score "
        "FROM chunks WHERE chunks MATCH ? ORDER BY score LIMIT 12",
        (match,),
    ).fetchall()

    # Gerbang relevansi: minimal 2 kata kunci harus muncul (atau 1 kalau pertanyaannya 1 kata).
    need = min(2, len(terms))
    hits = []
    for path, heading, body, score in rows:
        haystack = (path + " " + heading + " " + body).lower()
        matched = sum(1 for t in terms if t[: min(len(t), 5)] in haystack)
        if matched >= need:
            hits.append({"path": path, "heading": heading, "body": body, "score": score})
        if len(hits) == k:
            break
    return hits
