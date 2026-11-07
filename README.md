# JARVIS

Asisten suara pribadi berbasis model bahasa lokal (llamafile). Semua berjalan di komputer sendiri — tanpa API key, tanpa cloud.

Jarvis bisa:

- mengobrol dalam bahasa Indonesia atau Inggris (bahasanya menyesuaikan pertanyaan),
- mengingat fakta tentang kamu (`memory.json`),
- mencari jawaban dari folder dokumentasi Markdown lokal (SQLite FTS5),
- mencari info terkini di internet lewat DuckDuckGo (opsional),
- memberi peringatan kalau jawaban model menyebut nama/fakta yang tidak ada di sumber.

---

## Kebutuhan

| Kebutuhan | Keterangan |
|---|---|
| Python | 3.8 atau lebih baru |
| Model | file `*.llamafile` — unduh dari [Mozilla AI llamafile quickstart](https://docs.mozilla.ai/llamafile/getting-started/quickstart) (mis. `Qwen3.5-0.8B-Q8_0.llamafile`) |
| OS | macOS / Linux (Windows bisa, tapi `readline` perlu `pyreadline3`) |
| Paket Python | `requests` (wajib), `ddgs` (opsional, untuk pencarian web) |

> **Saya sarankan untuk buat python env dulu (venv)** sebelum install apa pun. Dengan begitu paket proyek ini tidak bercampur dengan Python sistem, dan kalau ada masalah cukup hapus folder `venv/` lalu ulangi.

---

## Instalasi

### 1. Masuk ke folder proyek

```bash
cd jarvis
```

### 2. Buat python env (venv) — sangat disarankan

```bash
python3 -m venv venv
```

Aktifkan venv-nya:

```bash
# macOS / Linux
source venv/bin/activate

# Windows (PowerShell)
venv\Scripts\Activate.ps1

# Windows (CMD)
venv\Scripts\activate.bat
```

Kalau berhasil, prompt terminal akan berawalan `(venv)`. Untuk keluar dari venv nanti: `deactivate`.

### 3. Install dependensi

```bash
pip install --upgrade pip
pip install requests
pip install ddgs        # opsional, untuk fitur pencarian web
```

### 4. Unduh model llamafile

Model LLM-nya diunduh dari dokumentasi resmi Mozilla AI:

**Panduan:** <https://docs.mozilla.ai/llamafile/getting-started/quickstart>

Model yang dipakai proyek ini adalah **Qwen3.5-0.8B-Q8_0** (lisensi Apache 2.0, ukuran ±1,77 GB). Unduh langsung:

<https://huggingface.co/mozilla-ai/llamafile_0.10/resolve/main/Qwen3.5-0.8B-Q8_0.llamafile>

Atau lewat terminal, simpan ke folder proyek:

```bash
curl -L -o Qwen3.5-0.8B-Q8_0.llamafile \
  https://huggingface.co/mozilla-ai/llamafile_0.10/resolve/main/Qwen3.5-0.8B-Q8_0.llamafile
```

Setelah terunduh, letakkan file-nya di folder ini:

```
jarvis/Qwen3.5-0.8B-Q8_0.llamafile
```

Beri izin eksekusi:

```bash
chmod +x Qwen3.5-0.8B-Q8_0.llamafile
```

Kalau macOS menolak menjalankannya karena "unidentified developer":

```bash
xattr -d com.apple.quarantine Qwen3.5-0.8B-Q8_0.llamafile
```

> **Windows:** tambahkan ekstensi `.exe` di akhir nama file (jadi `Qwen3.5-0.8B-Q8_0.llamafile.exe`).
>
> **Punya hardware/GPU lebih kuat?** Qwen3.5-0.8B adalah model terkecil yang tersedia sebagai llamafile, jadi paling mudah jalan. Untuk jawaban yang lebih akurat, kamu bisa memilih model lain yang lebih besar di daftar [pre-built llamafiles](https://docs.mozilla.ai/llamafile/getting-started/pre-built-llamafiles).

### 5. (Opsional) Siapkan dokumentasi pribadi

Buat folder `docs/` dan isi dengan file `.md`:

```bash
mkdir -p docs
```

Jarvis akan mengindeks otomatis semua file `.md` di folder itu (termasuk subfolder) ke `.jarvis_docs.db` saat pertama kali dijalankan.

---

## Menjalankan

Jarvis butuh **dua terminal**: satu untuk server model, satu untuk aplikasinya.

**Terminal 1 — jalankan server llamafile:**

```bash
./Qwen3.5-0.8B-Q8_0.llamafile --server --host 127.0.0.1 --port 8080 --nobrowser
```

Server harus sudah siap sebelum Jarvis dipakai. Alamatnya harus `http://localhost:8080` (lihat `BASE_URL` di `jarvis.py`).

> Secara default llamafile sudah menyajikan API yang kompatibel dengan OpenAI di `http://localhost:8080/v1` plus Web UI chat di <http://localhost:8080/>. Flag `--server` dipakai supaya llamafile hanya jalan sebagai server (tanpa chat interaktif di terminal).
>
> Tips macOS Apple Silicon: tambahkan `-ngl 9999` agar model jalan di GPU/Metal dan jauh lebih cepat.
> Tambahkan juga `-c 4096` kalau perlu konteks lebih panjang.

**Terminal 2 — jalankan Jarvis (venv harus aktif):**

```bash
source venv/bin/activate
python jarvis.py
```

Kalau semuanya benar, kamu akan melihat banner `JARVIS` dan info `model: ...` (bukan "tidak terhubung").

---

## Perintah di dalam aplikasi

| Perintah | Fungsi |
|---|---|
| `ingat nama_anak = Budi` | Simpan fakta ke `memory.json` |
| `/cari kata kunci` | Tes pencarian di folder dokumentasi (tanpa model) |
| `/web kata kunci` | Tes pencarian web (tanpa model) |
| `/auto on` / `/auto off` | Nyalakan/matikan pencarian web otomatis |
| `keluar`, `exit`, `quit`, atau `Ctrl+C` | Keluar |

---

## Konfigurasi

Bisa lewat variabel lingkungan:

| Variabel | Default | Fungsi |
|---|---|---|
| `JARVIS_DOCS` | `./docs` | Folder dokumentasi Markdown |
| `JARVIS_DB` | `./.jarvis_docs.db` | Lokasi database indeks dokumentasi |

Contoh:

```bash
JARVIS_DOCS=~/Catatan python jarvis.py
```

Pengaturan lain (alamat server, jumlah hasil, batas panjang konteks) ada di bagian atas `jarvis.py`.

---

## Struktur proyek

```
jarvis/
├── jarvis.py              # program utama (UI, prompt, streaming jawaban)
├── docs_index.py          # indeks & pencarian dokumentasi Markdown (SQLite FTS5)
├── web_search.py          # pencarian DuckDuckGo + heuristik kapan perlu cari
├── memory.json            # fakta pribadi (dibuat otomatis, tidak di-commit)
├── .jarvis_docs.db        # indeks dokumentasi (dibuat otomatis, tidak di-commit)
├── docs/                  # catatan Markdown kamu (opsional, tidak di-commit)
├── venv/                  # python env (tidak di-commit)
└── *.llamafile            # model lokal (tidak di-commit)
```

File `memory.json`, `.jarvis_docs.db`, folder `docs/`, `venv/`, dan file `*.llamafile` sudah masuk `.gitignore` karena berisi data pribadi atau berukuran besar.

---

## Troubleshooting

**`model: tidak terhubung`**
Server llamafile belum jalan atau port-nya bukan 8080. Jalankan lagi perintah di Terminal 1 dan pastikan tidak ada error.

**`Tidak bisa terhubung ke llamafile`**
Sama seperti di atas — cek server, cek port, cek `BASE_URL` di `jarvis.py`.

**`ddgs belum terpasang`**
Jalankan `pip install ddgs` **di dalam venv yang aktif**.

**`SQLite di Python ini tidak mendukung FTS5`**
Biasanya terjadi pada Python hasil kompilasi sendiri tanpa FTS5. Pakai Python dari python.org atau Homebrew (`brew install python`).

**Pencarian dokumentasi tidak menemukan apa pun**
Pastikan folder `docs/` ada dan berisi file `.md`, lalu tes dengan `/cari kata kunci`.

**Model lambat**
Tambahkan `-ngl 9999` saat menjalankan llamafile (butuh GPU/Metal). Model 0.8B kuantisasi Q8 tetap butuh RAM sekitar 1 GB.

---

## Catatan

- Riwayat obrolan hanya hidup selama program berjalan; yang tersimpan permanen hanyalah `memory.json`.
- Jawaban yang ditandai `⚠ Tidak ada di cuplikan sumber` tidak dimasukkan ke riwayat, supaya nama karangan model tidak terbawa ke pertanyaan berikutnya.
- Proyek ini tidak memakai API berbayar. Model, pencarian, dan indeks semuanya lokal.
