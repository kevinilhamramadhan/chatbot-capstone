# Baseline Eval — `qwen3.5:0.8b` (SEBELUM fine-tuning)

- Tanggal: 2026-07-04 · 100 baris `data/test.jsonl` (held-out) · durasi 3.202 dtk (CPU)
- Jalur eval = jalur serving produksi (ChatOllama + bind_tools, sampling produksi)
- Data mentah: `results_qwen3.5_0.8b.json` · Harness: `eval_tool_calling.py`
- **Inilah angka yang harus dikalahkan model hasil fine-tuning (`toti-qwen`).**

## Skor agregat

| Metrik | Skor | Target setelah fine-tune |
|---|---|---|
| function_selection_acc (tool yang benar) | **41,7%** | ≥ 80% |
| param_exact_acc (argumen persis benar) | **30,0%** | ≥ 65% |
| irrelevance_acc (tahu kapan TIDAK memanggil tool) | **57,5%** | ≥ 80% |
| false_tool_rate (asal manggil tool) | **42,5%** | ≤ 15% |
| invalid_call_rate (format call rusak) | 0,0% | tetap ~0 |

## Per kategori — baris tool (n / tool benar / argumen persis)

| Tipe | Tool | n | sel | param | Catatan |
|---|---|---|---|---|---|
| T1 | get_menu | 9 | 8 | 8 | sudah kuat |
| T2 | get_menu (kategori) | 4 | 2 | 1 | |
| T3 | get_product_detail | 9 | 4 | 1 | nama produk sering tidak canonical |
| T4 | compare_products | 5 | 1 | 0 | lemah |
| T5 | add_to_cart (1 item) | 7 | **0** | 0 | **terparah — inti bisnis** |
| T6 | add_to_cart (multi) | 4 | **0** | 0 | **terparah** |
| T7 | add_to_cart (via history) | 4 | 2 | 0 | |
| T8 | get_order_status | 6 | 4 | 4 | lumayan |
| T9 | cancel_order | 4 | 1 | 1 | |
| T10 | escalate_to_admin | 4 | **0** | 0 | **kue custom tak pernah diteruskan** |
| T11 | financial_report | 2 | 2 | 2 | ok |
| T12 | business_analytics | 2 | 1 | 1 | |

## Per kategori — baris non-tool (n / benar diam / salah manggil tool)

| Tipe | Skenario | n | ok | false_tool | Catatan |
|---|---|---|---|---|---|
| N1 | FAQ ber-konteks | 11 | 8 | 3 | |
| N2 | Info tak tersedia | 3 | 2 | 1 | |
| N3 | Sapaan/terima kasih | 6 | 5 | 1 | |
| N4 | Out-of-scope | 8 | 6 | 2 | |
| N5 | Ambigu → harus tanya balik | 7 | **1** | 6 | **asal call, bukan bertanya** |
| N6 | Adversarial ("cara batalin gimana?") | 5 | **1** | 4 | **"how-to" dieksekusi beneran** |

## Kesimpulan

Base model hanya andal untuk get_menu & laporan Owner. Kegagalan terkonsentrasi
persis di perilaku yang dataset 800-baris ini latih: menerima pesanan
(add_to_cart 0/11 gabungan T5+T6), eskalasi kue custom (0/4), bertanya balik
saat ambigu (1/7), dan menahan diri pada kalimat jebakan (1/5). Ruang naiknya
besar dan terukur — pasca fine-tuning, jalankan harness dengan `--model
toti-qwen` lalu bandingkan berdampingan dengan tabel ini.

## Catatan teknis

- `temperature=0` DILARANG di eval/serving model ini — greedy decoding membuat
  0.8B loop tanpa henti (insiden: 1 request berjalan 1,5 jam). Harness sudah
  memakai sampling produksi + `num_predict=768`.
- Skor bisa bergeser ±beberapa poin antar-run (sampling stokastik); perbaikan
  yang berarti harus jauh di atas noise itu (puluhan poin, sesuai target).
