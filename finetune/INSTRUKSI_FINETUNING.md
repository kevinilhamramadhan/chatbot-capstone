# Instruksi Fine-Tuning `qwen3.5:0.8b` — Toti Cakery Tool-Calling

> Dokumen serah-terima untuk session baru. Minta saja: *"buatkan kode fine-tuning
> sesuai `finetune/INSTRUKSI_FINETUNING.md`"* — semua keputusan sudah diambil di
> sini, tinggal implementasi.

## 0. Tujuan & definisi sukses

Melatih LoRA di atas `qwen3.5:0.8b` agar chatbot **lebih akurat memanggil 9 tool**
tanpa kehilangan kemampuan percakapan. Sukses = skor harness pada `test.jsonl`
naik jelas dari baseline (BUKAN dari loss):

| Metrik | Baseline (results_qwen3.5_0.8b.json) | Target |
|---|---|---|
| function_selection_acc | 0.417 | ≥ 0.80 |
| param_exact_acc | 0.300 | ≥ 0.65 |
| irrelevance_acc | 0.575 | ≥ 0.80 |
| false_tool_rate | 0.425 | ≤ 0.15 |
| invalid_call_rate | 0.000 | tetap ~0 |

Kelemahan baseline yang paling harus terangkat: `add_to_cart` (0/11!),
`escalate_to_admin` (0/4), kasus ambigu N5 (bertanya balik, bukan asal call),
adversarial N6 ("cara batalin gimana?" ≠ cancel_order).

## 1. Dataset

- HuggingFace: `KEVIN_HF_USERNAME/toti-cakery-toolcall` (atau lokal `finetune/data/`).
- 3 split: `train` 800 / `validation` 80 (iid, untuk val-loss) / `test` 100
  (held-out, HANYA untuk harness — jangan pernah masuk training/val).
- Format per baris: `messages` (system+history+user+final assistant),
  `tools_json` (string berisi 9 skema tool), `meta` (abaikan saat training).
- **PENTING**: `tool_calls[].function.arguments` disimpan sebagai **JSON string**
  → parse jadi dict SEBELUM `apply_chat_template`; `tools_json` juga di-parse.
  Cell konversi lengkap ada di `finetune/README.md` bagian
  "Using with the Unsloth Colab" — pakai itu apa adanya.

## 2. Setup training (Unsloth, Colab T4 cukup)

- **Template resmi Unsloth tersedia di repo: `finetune/Qwen3_5_(0_8B)_Vision.ipynb`**
  (diunduh dari unslothai/notebooks — satu-satunya varian resmi utk 0.8B; Qwen3.5
  multimodal, tapi fine-tuning kita text-only). **Tulis kode DARI notebook ini**,
  jangan dari ingatan: pakai cell instalasi, loading model, `get_peft_model`,
  `SFTTrainer`/`SFTConfig`, dan cell export-nya apa adanya; hanya bagian *data
  prep* yang diganti dengan cell konversi dataset kita (README §Colab). Karena
  data kita text-only, muat model lewat jalur teks (`FastLanguageModel` — di
  notebook tertulis sebagai komentar pada import `FastVisionModel`).
- Base model: varian instruct Qwen3.5 0.8B dari Unsloth (yang setara dengan
  `qwen3.5:0.8b` di Ollama). `load_in_4bit=True` boleh; model kecil, T4 longgar.
- `max_seq_length = 4096` (prompt terpanjang ±3k token: system+tools+history).
- Rendering: `tokenizer.apply_chat_template(messages, tools=tools, tokenize=False,
  add_generation_prompt=False)` → kolom `text`. **Sanity cell wajib** sebelum
  training: print 1 sampel ter-render, pastikan ada blok `<tools>` dan
  `<tool_call>` yang benar (baris tool-call) — kalau tidak ada, format salah.
- **Masking**: `train_on_responses_only` dengan marker keluarga Qwen:
  `instruction_part="<|im_start|>user\n"`, `response_part="<|im_start|>assistant\n"`.
  Verifikasi marker terhadap `tokenizer.chat_template` aktual (jangan hafalan).
- LoRA: r=16, alpha=16, dropout=0, target semua proyeksi linear
  (q,k,v,o,gate,up,down). Seed 42.
- Trainer: lr=2e-4 (cosine/linear), warmup 5–10 step, epoch 2 (naikkan ke 3
  hanya kalau val-loss masih turun), per_device_batch=2 + grad_accum=4–8
  (batch efektif 8–16), `eval_dataset=validation`, `eval_strategy="steps"`
  (mis. tiap 25 step).
- **Aturan berhenti**: val-loss naik 2 evaluasi berturut-turut → stop, pakai
  checkpoint sebelum kenaikan. Loss train yang terus turun sendiri BUKAN sinyal
  bagus.

## 3. Export → Ollama

1. Simpan GGUF via Unsloth (`save_pretrained_gguf`), quantization `q8_0`
   (model cuma 0.8B — q8 tetap kecil ±1GB dan kualitas hampir utuh; q4_k_m
   fallback kalau mau lebih kecil).
2. Ambil template asli: `ollama show qwen3.5:0.8b --template` (dan `--parameters`).
3. Modelfile: `FROM ./model.gguf` + `TEMPLATE` **persis sama dengan base** +
   parameter bawaan. **Template beda = penyebab #1 "kok jadi bodoh setelah
   export"** (per dokumentasi Unsloth).
4. `ollama create toti-qwen -f Modelfile`.

## 4. Evaluasi (wajib, di mesin ini)

```bash
cd /home/kevin/clcode/chatbot
chatbot-service/.venv/bin/python finetune/eval_tool_calling.py --model toti-qwen
# bandingkan finetune/results_toti-qwen.json vs finetune/results_qwen3.5_0.8b.json
```

- Harness sudah memakai jalur serving produksi persis (ChatOllama + bind_tools
  + sampling produksi). ±30 detik/baris di CPU → ±50 menit; jalankan background.
- **JANGAN set temperature 0** di harness/Ollama — greedy decoding membuat model
  0.8B loop tanpa henti (sudah kejadian: 1 request macet 1,5 jam). `num_predict`
  cap sudah terpasang di harness.
- Lolos target §0 → ganti `LLM_MODEL=toti-qwen` di `.env`, jalankan
  `python -m scripts.chat_cli` untuk smoke percakapan nyata, lalu 26 unit test
  (`pytest chatbot-service/tests/`) tetap harus hijau.
- Gagal target → urutan diagnosis: (1) cek sanity render (template!), (2) cek
  masking benar (loss hanya di response), (3) coba 3 epoch / lr 1e-4,
  (4) bandingkan per-type di JSON hasil: tipe yang jeblok menunjukkan bagian
  dataset yang perlu diperbanyak — generator (`generate_dataset.py`) tinggal
  diubah count-nya dan digenerate ulang.

## 5. Jangan dilakukan

- Jangan melatih dari split `test` atau menyentuh isinya.
- Jangan mengubah system prompt / skema tool di dataset agar "lebih mudah" —
  parity dengan produksi adalah alasan dataset ini dibuat.
- Jangan menilai keberhasilan dari contoh manual satu-dua chat; angka harness
  adalah satu-satunya verdict.
- Jangan pakai Modelfile tanpa TEMPLATE eksplisit dari base model.
