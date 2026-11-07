"""Pencarian internet untuk Jarvis (DuckDuckGo lewat paket `ddgs`) + penentu kapan perlu mencari."""
import importlib.util
import re


def available():
    """True kalau paket ddgs sudah terpasang."""
    return importlib.util.find_spec("ddgs") is not None


def search_web(query, k=4, timeout=8):
    """Cari di web. Return (hasil, error). hasil = list of {title, url, snippet}."""
    try:
        from ddgs import DDGS
    except ImportError:
        return [], "paket ddgs belum terpasang (jalankan: pip install ddgs)"
    try:
        raw = DDGS(timeout=timeout).text(query, max_results=k)
    except Exception as e:  # jaringan mati, diblokir, timeout, dll.
        msg = str(e)
        if "No results" in msg:
            return [], None
        return [], f"pencarian gagal: {msg[:120] or type(e).__name__}"
    results = [
        {
            "title": (r.get("title") or "").strip(),
            "url": (r.get("href") or r.get("url") or r.get("link") or "").strip(),
            "snippet": " ".join((r.get("body") or "").split()),
        }
        for r in (raw or [])
    ]
    return results, None


# ------------------------------------------------------------------ Merapikan kueri
FILLER_WORDS = {
    "tolong", "carikan", "cari", "coba", "kayaknya", "sepertinya", "kira", "dong", "deh", "sih",
    "apa", "aja", "saja", "mengenai", "tentang", "soal", "banyak", "info", "informasi",
    "kamu", "anda", "tahu", "apakah", "please", "can", "you", "tell", "me", "about", "do", "know",
}


def clean_query(text):
    """Buang kata pengisi supaya kueri pencarian lebih tajam ("Cari banyak info, mengenai X" -> "X")."""
    words = re.findall(r"[\w'-]+", text)
    kept = [w for w in words if w.lower() not in FILLER_WORDS]
    return " ".join(kept) if kept else text.strip()


# ------------------------------------------------------------------ Kapan perlu mencari?
# Pertanyaan tentang tanggal/jam SEKARANG: dijawab langsung dari jam sistem (tanpa model, tanpa web).
DATE_NOW_RE = re.compile(
    r"(tanggal berapa( hari ini| sekarang| ini)?\s*[?.!]*\s*$|tanggal (hari ini|sekarang)|(hari ini|sekarang) tanggal|"
    r"(sekarang|hari ini|ini) hari apa|hari apa (sekarang|ini|hari ini)|"
    r"sekarang jam berapa|jam berapa (sekarang|ini)|pukul berapa sekarang|"
    r"sekarang tahun berapa|tahun berapa (sekarang|ini)|"
    r"sekarang bulan apa|bulan apa (sekarang|ini)|"
    r"today'?s? date|today date|date today|date now|"
    r"what('s| is) the (current )?date|what date is (it|today)|current date|"
    r"what day is (it|today)|what day of the week is (it|today)|"
    r"what time is it|what('s| is) the (current )?time|current time|time now|"
    r"what year is it|what month is it)"
)

# Versi lebih longgar: kalau cocok, jangan cari di web (tapi tidak dijawab langsung).
DATE_RE = re.compile(
    r"(tanggal berapa|hari apa|jam berapa|pukul berapa|bulan apa|tahun berapa|"
    r"what (time|date|day)|what's the (time|date))"
)


def is_date_question(question):
    """True kalau pertanyaannya tentang tanggal/jam sekarang."""
    return bool(DATE_NOW_RE.search(question.lower()))

# Penanda info yang berubah-ubah / terkini.
CURRENT_RE = re.compile(
    r"(hari ini|saat ini|sekarang|terbaru|terkini|terakhir|berita|kabar terbaru|harga|kurs|"
    r"cuaca|skor|hasil pertandingan|jadwal|trending|rilis|update|tahun ini|bulan ini|"
    r"minggu ini|latest|current|currently|today|news|price|weather|score|right now|"
    r"this year|this week|release)"
)

# Kata tanya fakta.
FACT_RE = re.compile(
    r"\b(siapa|kapan|berapa|dimana|di mana|apa itu|apakah|who|when|where|"
    r"how many|how much|what is|what are|which)\b"
)

# Pertanyaan "kamu tahu X?" / "ceritakan tentang X": minta info soal sesuatu yang spesifik.
KNOW_RE = re.compile(
    r"(\b(kamu|anda|apa kamu|apakah kamu) (tahu|kenal)\b|\btahu (tentang|soal|mengenai)\b|"
    r"\bkenal\b|do you know|tell me about|what do you know|"
    r"\bceritakan (tentang|soal)\b|\bjelaskan (tentang|soal)\b|"
    r"\binfo(rmasi)? (tentang|soal|mengenai)\b)"
)

# Permintaan kreatif/olah teks: tidak perlu web.
CREATIVE_RE = re.compile(
    r"\b(buatkan|tuliskan|tulis|terjemahkan|translate|write|compose|ringkas|summarize|"
    r"koreksi|perbaiki|rewrite|puisi|poem|cerita|story|lagu|song)\b"
)

# Kata ganti orang pertama: biasanya pertanyaan tentang diri sendiri (jawabannya di memori).
PERSONAL_RE = re.compile(r"\b(saya|aku|ku|punyaku|my|mine|me|i)\b")

# Hitungan sederhana ("what is 2+2") tidak perlu web.
MATH_RE = re.compile(r"\d+\s*[+\-*/x\u00d7\u00f7]\s*\d+")

# Huruf kapital di tengah kalimat yang bukan kata ganti/sapaan: kemungkinan nama (produk, aplikasi, orang).
IGNORE_CAPS = {"jarvis", "anda", "kamu", "saya", "aku", "halo", "hai", "hello"}


def _has_proper_noun(question):
    for m in re.finditer(r"\b[A-Z][A-Za-z0-9]{2,}\b", question):
        word = m.group()
        if m.start() == 0 or word.lower() in IGNORE_CAPS:
            continue
        if word.isupper() and len(word) <= 4:  # singkatan umum (API, JSON, SQL)
            continue
        if question[: m.start()].rstrip().endswith((".", "?", "!")):  # awal kalimat berikutnya
            continue
        return True
    return False


# Pertanyaan yang ditujukan ke Jarvis sendiri ("kamu siapa?", "who are you?"): tidak perlu web.
ASSISTANT_RE = re.compile(
    r"(kamu siapa|siapa kamu|anda siapa|siapa anda|siapa (nama|namamu)|nama (kamu|mu|anda)|"
    r"kamu (itu )?(apa|siapa)|kamu bisa (apa|ngapain)|apa yang (bisa|dapat) kamu|"
    r"dibuat (oleh )?siapa|siapa yang (membuat|menciptakan) (kamu|mu)|kamu pakai model|"
    r"who are you|what are you|what('s| is) your name|what can you do|who (made|created|built) you)"
)

# Kata tanya dan kata penghubung: kalau hanya ini yang tersisa, tidak ada yang layak dicari.
QUESTION_WORDS = {
    "siapa", "kapan", "berapa", "dimana", "mana", "apa", "apakah", "bagaimana", "gimana",
    "kenapa", "mengapa", "who", "what", "when", "where", "which", "how", "why", "is", "are",
    "was", "were", "the", "an", "of", "to", "in", "on", "this", "that", "they", "them",
    "here", "there", "ini", "itu", "dia", "mereka",
}


def _content_words(text):
    return [
        w for w in re.findall(r"[\w'-]+", text.lower())
        if w not in FILLER_WORDS and w not in QUESTION_WORDS and len(w) > 2
    ]


def needs_web(question, mem):
    """Tebak apakah pertanyaan ini butuh pencarian web. Heuristik sederhana, bisa disetel."""
    q = question.lower().strip()
    if len(re.findall(r"\w+", q)) < 2:  # sapaan / satu kata
        return False
    if is_date_question(q) or DATE_RE.search(q):
        return False
    # Menyebut nilai di memori (misal nama anak) -> pertanyaan pribadi
    for value in mem.values():
        v = str(value).lower().strip()
        if len(v) >= 3 and v in q:
            return False
    if ASSISTANT_RE.search(q):
        return False
    if CURRENT_RE.search(q):
        return True
    if PERSONAL_RE.search(q) or CREATIVE_RE.search(q) or MATH_RE.search(q):
        return False
    if not _content_words(question):  # hanya kata tanya, tidak ada topik yang bisa dicari
        return False
    if FACT_RE.search(q) or KNOW_RE.search(q):
        return True
    return _has_proper_noun(question)


# ------------------------------------------------------------------ Pertanyaan lanjutan
FOLLOWUP_WORDS = {
    "iya", "ya", "yap", "yup", "ok", "oke", "okay", "lanjut", "lanjutkan", "semuanya", "semua",
    "boleh", "tolong", "dong", "terus", "lalu", "lagi", "lebih", "detail", "rinci", "lengkap",
    "jelaskan", "ceritakan", "yes", "yeah", "sure", "please", "go", "on", "continue", "more",
    "tell", "me", "about", "it", "that", "all", "and", "then", "details", "detailed",
}


def is_followup(text):
    """True kalau pesan ini hanya jawaban singkat seperti 'iya' / 'semuanya' / 'tell me more'."""
    words = re.findall(r"\w+", text.lower())
    return 0 < len(words) <= 4 and all(w in FOLLOWUP_WORDS for w in words)