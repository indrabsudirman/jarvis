import json
import os
import re
import sys
from datetime import datetime

import requests

import docs_index
import web_search

try:
    import readline  # noqa: F401  (membuat input() bisa pakai panah kiri/kanan/atas)
    HAS_READLINE = True
except ImportError:
    HAS_READLINE = False

# ---------------------------------------------------------------- Konfigurasi
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MEMORY_FILE = os.path.join(BASE_DIR, "memory.json")

# Folder dokumentasi (.md). Ubah di sini, atau set env var JARVIS_DOCS.
DOCS_DIR = os.environ.get("JARVIS_DOCS", os.path.join(BASE_DIR, "docs"))

BASE_URL = "http://localhost:8080"  # alamat server llamafile
CHAT_URL = BASE_URL + "/v1/chat/completions"
MODELS_URL = BASE_URL + "/v1/models"

VERSION = "0.6.1"
DOCS_TOP_K = 3          # jumlah potongan dokumentasi yang dikirim ke model
DOCS_MAX_CHARS = 1200   # batas panjang tiap potongan di prompt
WEB_TOP_K = 4           # jumlah hasil web yang dikirim ke model
WEB_MAX_CHARS = 400     # batas panjang cuplikan tiap hasil web
WEB_AUTO = True         # cari web otomatis untuk pertanyaan fakta/terkini (ubah live: /auto on|off)

# ---------------------------------------------------------------- Warna ANSI
GREEN = "\033[38;5;156m"   # hijau muda, mirip banner llamafile
BRIGHT = "\033[92m"        # hijau terang untuk prompt
YELLOW = "\033[93m"
BOLD = "\033[1m"
DIM = "\033[2m"
RESET = "\033[0m"

# \001 dan \002 memberi tahu readline bahwa kode warna tidak punya lebar,
# supaya kursor tidak bergeser saat mengetik.
if HAS_READLINE:
    PROMPT = f"\001{BRIGHT}\002>>> \001{GREEN}\002"
else:
    PROMPT = f"{BRIGHT}>>> {GREEN}"

# ---------------------------------------------------------------- Banner
FONT = {
    "J": ["  ███", "   █ ", "   █ ", "█  █ ", " ██  "],
    "A": [" ███ ", "█   █", "█████", "█   █", "█   █"],
    "R": ["████ ", "█   █", "████ ", "█  █ ", "█   █"],
    "V": ["█   █", "█   █", "█   █", " █ █ ", "  █  "],
    "I": ["█████", "  █  ", "  █  ", "  █  ", "█████"],
    "S": [" ████", "█    ", " ███ ", "    █", "████ "],
}


def print_banner():
    rows = [""] * 5
    for ch in "JARVIS":
        for i, line in enumerate(FONT[ch]):
            rows[i] += "".join("██" if c == "█" else "  " for c in line) + "  "
    print()
    print(GREEN + "\n".join(rows) + RESET)
    print()


def get_model_name():
    """Tanya server llamafile model apa yang sedang aktif. None kalau tidak terhubung."""
    try:
        r = requests.get(MODELS_URL, timeout=3)
        data = r.json()
        items = data.get("data") or data.get("models") or []
        if items:
            first = items[0]
            return first.get("id") or first.get("name") or first.get("model") or "local"
        return "local"
    except Exception:
        return None


def short_path(path):
    home = os.path.expanduser("~")
    return "~" + path[len(home):] if path.startswith(home) else path


def web_status():
    if not web_search.available():
        return f"{YELLOW}ddgs belum terpasang (pip install ddgs){RESET}"
    return "otomatis (DuckDuckGo)" if WEB_AUTO else "manual (/web kata kunci)"


def print_info(mem, docs_status):
    model = get_model_name()
    rows = [
        ("software", f"jarvis {VERSION}"),
        ("model", model if model else f"{YELLOW}tidak terhubung{RESET}"),
        ("memory", f"memory.json ({len(mem)} fakta)"),
        ("docs", docs_status),
        ("web", web_status()),
        ("server", BASE_URL),
    ]
    for label, value in rows:
        print(f"{BOLD}{label + ':':<10}{RESET}{value}")
    print()
    print(f"{DIM}Simpan fakta : ingat nama_anak = Budi{RESET}")
    print(f"{DIM}Tes dokumen  : /cari kata kunci{RESET}")
    print(f"{DIM}Tes web      : /web kata kunci     |  matikan/nyalakan otomatis: /auto off, /auto on{RESET}")
    print(f"{DIM}Keluar       : ketik 'keluar' atau tekan Ctrl+C{RESET}")
    print()


# ---------------------------------------------------------------- Bahasa
EN_WORDS = {
    "what", "is", "the", "are", "was", "were", "who", "how", "when", "where", "why", "which",
    "do", "does", "did", "can", "could", "would", "should", "you", "your", "my", "me", "i",
    "we", "to", "of", "in", "on", "it", "this", "that", "and", "or", "please", "tell",
    "today", "date", "time", "now", "name", "have", "has", "with", "for", "about",
}
ID_WORDS = {
    "apa", "siapa", "yang", "dan", "di", "ke", "dari", "untuk", "dengan", "tidak", "saya",
    "aku", "kamu", "anda", "ini", "itu", "hari", "tanggal", "berapa", "bagaimana", "gimana",
    "kenapa", "mengapa", "kapan", "dimana", "bisa", "tolong", "sekarang", "adalah", "atau",
    "pada", "akan", "sudah", "apakah", "kalo", "kalau", "nama", "anak", "punya", "ada",
}


def detect_lang(text):
    """Tebak bahasa pertanyaan: 'en' atau 'id' (default 'id' kalau seri)."""
    words = re.findall(r"[a-zA-Z']+", text.lower())
    en = sum(w in EN_WORDS for w in words)
    idn = sum(w in ID_WORDS for w in words)
    return "en" if en > idn else "id"


# ---------------------------------------------------------------- Tanggal & waktu
HARI = ["Senin", "Selasa", "Rabu", "Kamis", "Jumat", "Sabtu", "Minggu"]
BULAN = [
    "Januari", "Februari", "Maret", "April", "Mei", "Juni",
    "Juli", "Agustus", "September", "Oktober", "November", "Desember",
]
WEEKDAYS_EN = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
MONTHS_EN = [
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
]


def now_text(lang="id"):
    """Tanggal dan jam sekarang (dari jam sistem Mac)."""
    n = datetime.now().astimezone()
    if lang == "en":
        clock = n.strftime("%I:%M %p").lstrip("0")
        return f"{WEEKDAYS_EN[n.weekday()]}, {MONTHS_EN[n.month - 1]} {n.day}, {n.year}, {clock} {n.tzname()}"
    return f"{HARI[n.weekday()]}, {n.day} {BULAN[n.month - 1]} {n.year}, pukul {n:%H.%M} {n.tzname()}"


def date_answer(lang):
    """Jawaban langsung untuk pertanyaan tanggal/jam. Selalu benar karena dari jam sistem."""
    if lang == "en":
        return f"It's {now_text('en')}."
    return f"Sekarang {now_text('id')}."


# ---------------------------------------------------------------- Memori
def load_memory():
    """Baca memory.json dan ubah jadi dictionary Python."""
    if os.path.exists(MEMORY_FILE):
        with open(MEMORY_FILE, encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_memory(mem):
    """Tulis dictionary ke memory.json."""
    with open(MEMORY_FILE, "w", encoding="utf-8") as f:
        json.dump(mem, f, ensure_ascii=False, indent=2)


# ---------------------------------------------------------------- Dokumentasi
def open_docs():
    """Buka indeks dokumentasi dan sinkronkan. Return (conn, status_teks)."""
    if not os.path.isdir(DOCS_DIR):
        return None, f"{YELLOW}folder tidak ditemukan: {short_path(DOCS_DIR)}{RESET}"
    try:
        conn = docs_index.connect()
        docs_index.sync(DOCS_DIR, conn)
    except Exception as e:
        return None, f"{YELLOW}tidak aktif ({e}){RESET}"
    n_files, n_chunks = docs_index.stats(conn)
    return conn, f"{short_path(DOCS_DIR)} ({n_files} file, {n_chunks} bagian)"


def refresh_docs(conn):
    """Panggil sebelum tiap pertanyaan: murah, dan menangkap dokumen yang baru ditulis."""
    if conn is None:
        return
    try:
        added, updated, removed = docs_index.sync(DOCS_DIR, conn)
    except Exception:
        return
    if added or updated or removed:
        print(f"{DIM}(dokumentasi diperbarui: +{added} baru, {updated} diubah, -{removed} dihapus){RESET}")


def print_doc_sources(hits):
    for i, h in enumerate(hits, 1):
        print(f"{DIM}[{i}] {h['path']} › {h['heading']}{RESET}")
    print()


# ---------------------------------------------------------------- Web
def do_web_search(query):
    """Cari di internet sambil menampilkan status. Return list hasil (bisa kosong)."""
    query = web_search.clean_query(query)
    print(f"{DIM}Mencari di internet: {query}{RESET}")
    results, error = web_search.search_web(query, k=WEB_TOP_K)
    if error:
        print(f"{YELLOW}{error}{RESET}")
    elif not results:
        print(f"{DIM}(tidak ada hasil web){RESET}")
    return results


def print_web_sources(results):
    for i, r in enumerate(results, 1):
        print(f"{DIM}[{i}] {r['title']} — {r['url']}{RESET}")
    print()


# ---------------------------------------------------------------- Prompt
GROUNDING = {
    "id": (
        "ATURAN PENTING: hanya sebut nama, angka, dan fakta yang benar-benar tertulis di sumber di atas. "
        "Jangan menambah contoh atau nama dari ingatanmu. "
        "Jangan setuju dengan pengguna hanya karena ia menyatakannya: periksa dulu pada sumber, "
        "dan kalau tidak ada di sumber, katakan 'tidak ditemukan di sumber'."
    ),
    "en": (
        "IMPORTANT: only mention names, numbers, and facts that are actually written in the sources above. "
        "Do not add examples or names from your own memory. "
        "Do not agree with the user just because they said so: check the sources first, "
        "and if it is not there, say 'not found in the sources'."
    ),
}


def build_system(lang, mem, hits, web):
    """Susun system prompt dalam bahasa yang sama dengan pertanyaan.

    Model kecil cenderung mengikuti bahasa system prompt, jadi prompt-nya ikut diganti.
    """
    facts = "\n".join(f"- {k}: {v}" for k, v in mem.items())
    has_ctx = bool(hits or web)

    if lang == "en":
        length = "at most 3-4 sentences" if has_ctx else "at most 1-2 sentences"
        system = (
            "You are Jarvis, the user's personal voice assistant. Always reply in English. "
            f"Use natural, short, conversational sentences, {length}. "
            "Do not use lists, bullets, bold text, or markdown. "
            "Do not offer extra help and do not ask questions back unless asked. "
            "If you do not know or are not sure, say so plainly; do not make things up. "
            f"Current date and time: {now_text('en')}. "
            "Use it for 'today', 'tomorrow', or 'this year', and never guess the date from memory. "
            "Your knowledge may be outdated, so rely on search results for current facts when available. "
            "Answer directly, using these facts about the user:\n" + facts
        )
        if hits:
            ctx = "\n\n".join(
                f"[{i}] ({h['path']} › {h['heading']})\n{h['body'][:DOCS_MAX_CHARS]}"
                for i, h in enumerate(hits, 1)
            )
            system += (
                "\n\nBelow are excerpts from the user's documentation. Answer based on them. "
                "If they do not contain the answer, say it is not in the documentation "
                "and do not make things up.\n\n" + ctx
            )
        elif web:
            ctx = "\n\n".join(
                f"[{i}] {r['title']} ({r['url']})\n{r['snippet'][:WEB_MAX_CHARS]}"
                for i, r in enumerate(web, 1)
            )
            system += (
                "\n\nBelow are recent web search results. Answer based on them and cite the "
                "source number, for example [1]. If they do not contain the answer, say you "
                "could not find it and do not make things up.\n\n" + ctx
            )
        if has_ctx:
            system += "\n\n" + GROUNDING["en"]
        return system

    length = "maksimal 3-4 kalimat" if has_ctx else "maksimal 1-2 kalimat"
    system = (
        "Kamu adalah Jarvis, asisten suara pribadi milik pengguna. Selalu jawab dalam bahasa Indonesia. "
        f"Gunakan kalimat percakapan yang natural dan singkat, {length}. "
        "Jangan pakai daftar, bullet, huruf tebal, atau format markdown. "
        "Jangan menawarkan bantuan tambahan dan jangan bertanya balik kecuali diminta. "
        "Jika kamu tidak tahu atau tidak yakin, katakan terus terang bahwa kamu tidak tahu; jangan mengarang. "
        f"Tanggal dan waktu sekarang: {now_text('id')}. "
        "Pakai ini untuk 'hari ini', 'besok', atau 'tahun ini', dan jangan menebak tanggal dari ingatanmu. "
        "Pengetahuanmu bisa sudah usang, jadi untuk fakta terkini andalkan hasil pencarian jika ada. "
        "Langsung sebut jawabannya berdasarkan fakta berikut tentang pengguna:\n" + facts
    )
    if hits:
        ctx = "\n\n".join(
            f"[{i}] ({h['path']} › {h['heading']})\n{h['body'][:DOCS_MAX_CHARS]}"
            for i, h in enumerate(hits, 1)
        )
        system += (
            "\n\nDi bawah ini ada kutipan dari dokumentasi pengguna. "
            "Jawab pertanyaan berdasarkan kutipan itu. "
            "Jika kutipan tidak memuat jawabannya, katakan bahwa hal itu tidak ada di "
            "dokumentasi dan jangan mengarang.\n\n" + ctx
        )
    elif web:
        ctx = "\n\n".join(
            f"[{i}] {r['title']} ({r['url']})\n{r['snippet'][:WEB_MAX_CHARS]}"
            for i, r in enumerate(web, 1)
        )
        system += (
            "\n\nDi bawah ini ada hasil pencarian web terbaru. "
            "Jawab pertanyaan berdasarkan hasil itu dan sebut nomor sumbernya, misalnya [1]. "
            "Jika hasilnya tidak memuat jawabannya, katakan kamu tidak menemukannya; "
            "jangan mengarang.\n\n" + ctx
        )
    if has_ctx:
        system += "\n\n" + GROUNDING["id"]
    return system


# ---------------------------------------------------------------- Cek pijakan jawaban
NEGATION_RE = re.compile(r"\b(tidak|bukan|belum|tak|not|no|never|n't)\b|n't")
SAFE_CAPS = (
    {"anda", "saya", "aku", "kamu", "jarvis", "ya", "tidak", "yes", "the"}
    | {x.lower() for x in HARI + BULAN + WEEKDAYS_EN + MONTHS_EN}
)


def ungrounded_names(answer, question, hits, web):
    """Cari nama (kata berawalan huruf kapital) di jawaban yang tidak ada di sumber.

    Ini penjaga sederhana, bukan pemeriksa fakta: nama yang muncul di jawaban tapi tidak
    ada di cuplikan sumber kemungkinan dikarang model.
    """
    if hits:
        source = " ".join(f"{h['path']} {h['heading']} {h['body'][:DOCS_MAX_CHARS]}" for h in hits)
    elif web:
        source = " ".join(f"{r['title']} {r['url']} {r['snippet'][:WEB_MAX_CHARS]}" for r in web)
    else:
        return []
    source = source.lower()
    negated = bool(NEGATION_RE.search(answer.lower()))
    question_lower = question.lower()

    flagged = []
    for m in re.finditer(r"\b[A-Z][A-Za-z0-9]{2,}\b", answer):
        word = m.group()
        low = word.lower()
        if low in SAFE_CAPS or low in flagged_lower(flagged):
            continue
        if answer[: m.start()].rstrip().endswith((".", "?", "!", ":")) or m.start() == 0:
            continue  # awal kalimat, belum tentu nama
        if re.fullmatch(r"\[?\d+\]?", word):
            continue
        if low in source:
            continue
        if negated and low in question_lower:  # "X tidak ditemukan": menyebut nama dari pertanyaan itu wajar
            continue
        flagged.append(word)
    return flagged[:5]


def flagged_lower(flagged):
    return {w.lower() for w in flagged}


# ---------------------------------------------------------------- Tanya model
def remember(history, user_text, answer):
    """Simpan giliran ini ke riwayat (maksimal 10 pesan terakhir).

    Kutipan dokumentasi/web sengaja tidak disimpan supaya konteks tidak membengkak.
    """
    if answer:
        history.append({"role": "user", "content": user_text})
        history.append({"role": "assistant", "content": answer})
        del history[:-10]


def ask(user_text, mem, history, hits, web):
    """Kirim pertanyaan ke model dan tampilkan jawabannya sambil mengalir (streaming)."""
    lang = detect_lang(user_text)
    system = build_system(lang, mem, hits, web)

    # Pengingat bahasa di ujung pesan: model kecil lebih patuh pada instruksi yang paling dekat.
    reminder = "(Please answer in English.)" if lang == "en" else "(Jawab dalam bahasa Indonesia.)"
    messages = (
        [{"role": "system", "content": system}]
        + history
        + [{"role": "user", "content": f"{user_text}\n\n{reminder}"}]
    )

    answer = ""
    with requests.post(
        CHAT_URL,
        json={
            "model": "local",
            "temperature": 0.3,
            "stream": True,
            "messages": messages,
        },
        stream=True,
        timeout=120,
    ) as r:
        r.raise_for_status()
        r.encoding = "utf-8"
        for raw in r.iter_lines(decode_unicode=True):
            if not raw or not raw.startswith("data:"):
                continue
            data = raw[5:].strip()
            if data == "[DONE]":
                break
            try:
                chunk = json.loads(data)
            except json.JSONDecodeError:
                continue
            choices = chunk.get("choices") or []
            if not choices:
                continue
            piece = (choices[0].get("delta") or {}).get("content")
            if piece:
                print(piece, end="", flush=True)
                answer += piece
    print("\n")
    return answer


# ---------------------------------------------------------------- Program utama
def main():
    global WEB_AUTO
    history = []  # riwayat obrolan, hanya hidup selama script jalan
    last_web = []  # hasil web terakhir, dipakai ulang untuk jawaban singkat seperti "iya"
    docs_conn, docs_status = open_docs()

    print_banner()
    print_info(load_memory(), docs_status)

    while True:
        try:
            text = input(PROMPT).strip()
        except (KeyboardInterrupt, EOFError):
            sys.stdout.write(RESET + "\n")
            break
        sys.stdout.write(RESET)  # kembalikan warna normal untuk jawaban

        if not text:
            continue
        if text.lower() in ("keluar", "exit", "quit"):
            break

        # Hidupkan/matikan pencarian web otomatis: "/auto on" atau "/auto off"
        if text.lower().startswith("/auto"):
            arg = text[5:].strip().lower()
            if arg in ("on", "off"):
                WEB_AUTO = arg == "on"
                print(f"Pencarian web otomatis: {'hidup' if WEB_AUTO else 'mati'}\n")
            else:
                print("Format: /auto on  atau  /auto off\n")
            continue

        # Tes pencarian web tanpa memanggil model: "/web kata kunci"
        if text.lower().startswith("/web "):
            results = do_web_search(text[5:].strip())
            for i, r in enumerate(results, 1):
                print(f"[{i}] {r['title']}\n    {r['url']}")
                print(f"{DIM}    {r['snippet'][:200]}...{RESET}")
            print()
            continue

        # Tes pencarian dokumentasi tanpa memanggil model: "/cari kata kunci"
        if text.lower().startswith("/cari "):
            refresh_docs(docs_conn)
            if docs_conn is None:
                print("Dokumentasi tidak aktif.\n")
                continue
            found = docs_index.search(docs_conn, text[6:], DOCS_TOP_K)
            if not found:
                print("Tidak ada hasil yang relevan.\n")
            for i, h in enumerate(found, 1):
                preview = " ".join(h["body"].split())[:200]
                print(f"[{i}] {h['path']} › {h['heading']}  (skor {h['score']:.2f})")
                print(f"{DIM}    {preview}...{RESET}")
            print()
            continue

        # Perintah menyimpan memori: "ingat kunci = nilai"
        if text.lower().startswith("ingat "):
            isi = text[6:]
            if "=" not in isi:
                print("Format: ingat nama_anak = Budi\n")
                continue
            kunci, nilai = isi.split("=", 1)
            mem = load_memory()
            mem[kunci.strip()] = nilai.strip()
            save_memory(mem)
            print(f"Oke, saya simpan {kunci.strip()} = {nilai.strip()}\n")
            continue

        # Pertanyaan tanggal/jam: dijawab langsung dari jam sistem (tanpa model dan tanpa web).
        if web_search.is_date_question(text):
            reply = date_answer(detect_lang(text))
            print(reply + "\n")
            remember(history, text, reply)
            continue

        # Pertanyaan biasa. Urutan: dokumentasi dulu, lalu web kalau perlu.
        refresh_docs(docs_conn)
        mem = load_memory()
        hits = docs_index.search(docs_conn, text, DOCS_TOP_K) if docs_conn else []
        web = []
        reused = False
        if not hits and WEB_AUTO:
            if web_search.needs_web(text, mem):
                web = do_web_search(text)
            elif last_web and web_search.is_followup(text):
                web, reused = last_web, True
                print(f"{DIM}(memakai hasil pencarian sebelumnya){RESET}")
        if web and not reused:
            last_web = web
        elif not web:
            last_web = []
        try:
            answer = ask(text, mem, history, hits, web)
            if answer and hits:
                print_doc_sources(hits)
            elif answer and web:
                print_web_sources(web)
            flagged = ungrounded_names(answer, text, hits, web) if answer else []
            if flagged:
                print(f"{YELLOW}⚠ Tidak ada di cuplikan sumber: {', '.join(flagged)}. "
                      f"Cek dulu, bisa jadi karangan model.{RESET}")
                print(f"{DIM}(jawaban ini tidak disimpan ke riwayat supaya tidak terbawa ke pertanyaan berikutnya){RESET}\n")
            else:
                remember(history, text, answer)
        except requests.exceptions.ConnectionError:
            print(f"{YELLOW}Tidak bisa terhubung ke llamafile. Pastikan servernya masih jalan.{RESET}\n")
        except requests.exceptions.RequestException as e:
            print(f"{YELLOW}Error saat menghubungi llamafile: {e}{RESET}\n")


if __name__ == "__main__":
    main()