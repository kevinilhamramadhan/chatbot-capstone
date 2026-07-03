---
license: mit
language:
  - id
  - en
task_categories:
  - text-generation
tags:
  - function-calling
  - tool-use
  - indonesian
  - unsloth
  - qwen
  - chatbot
pretty_name: Toti Cakery WhatsApp Chatbot — Tool-Calling SFT
size_categories:
  - n<1K
configs:
  - config_name: default
    data_files:
      - split: train
        path: data/train.jsonl
      - split: validation
        path: data/validation.jsonl
      - split: test
        path: data/test.jsonl
---

# Toti Cakery — Tool-Calling Fine-Tuning Dataset (qwen3.5:0.8b)

Synthetic bilingual (Indonesian ~79% / English ~21%) SFT dataset for a WhatsApp
cake-shop chatbot with **9 LangChain tools**. Goal: sharpen tool-calling
accuracy on a small model **without degrading conversational ability**
(60% tool-call rows : 40% conversation/refusal/clarification rows).

Built for the production system it serves — the system prompt, tool schemas
(generated from the live code via `convert_to_openai_tool`), and single-pass
serving contract are **bit-identical to runtime** (Ollama + `ChatOllama.bind_tools`).

## Row format

```json
{"messages": [
   {"role": "system", "content": "<production system prompt>[ + KONTEKS FAQ block]"},
   {"role": "user", "content": "aku mau cupcakes isi 6 coklat 2 kotak"},
   {"role": "assistant", "content": "",
    "tool_calls": [{"type": "function", "function": {
       "name": "add_to_cart",
       "arguments": "{\"items\":[{\"product\":\"Cupcakes isi 6 Cokelat\",\"qty\":2}]}"}}]}
 ],
 "tools_json": "<the 9 tool JSON schemas, serialized>",
 "meta": {"type": "T5", "lang": "id", "multi_turn": false, "noised": false}}
```

Key properties:

- **Single-pass tool calling**: rows end at the assistant `tool_calls` turn
  (production returns tool outputs verbatim; there is no second LLM pass, so
  there are no `tool` role turns to learn).
- `arguments` is a **JSON string** (parse it before `apply_chat_template` — see
  the Colab cell below). `tools_json` is a string for Arrow-schema stability.
- Multi-turn rows (~30%) carry up to 6 history messages, where assistant turns
  mimic real runtime outputs (menus with prices, cart summaries) — prices are
  allowed **only** there; final assistant turns never state prices/stock from
  memory (that data comes from tools at runtime).
- Non-tool rows teach the decision boundary: grounded FAQ answers, greeting
  small talk, out-of-scope refusals, ambiguous→clarifying-question (missing
  size/isi/flavour), and adversarial near-negatives ("cara batalin gimana?"
  must NOT call `cancel_order`).

## Splits

| Split | Rows | Purpose |
|---|---|---|
| `train` | 800 | weight updates |
| `validation` | 80 | same distribution as train (iid) — pass as `eval_dataset` to monitor val-loss / early stopping |
| `test` | 100 | **held-out**: ~15% of phrasing templates, 2 products (`Cake 22cm`, `Giant Cookies 15cm`), 1 flavour (`Matcha`), and 2 FAQ docs appear ONLY here. Used by the functional eval harness, never during training |

Composition (train): T1-T12 tool types 480 rows (add_to_cart family 130,
get_menu 100, detail 70, compare 40, status 50, cancel 30, escalate 35, owner
reports 25); non-tool 320 rows (FAQ-grounded 90, greetings 50, out-of-scope 60,
clarify 50, adversarial 45, no-info fallback 25). Validation/test keep the same
proportions. Zero verbatim (even punctuation-normalized) user-message overlap
across splits.

## Using with the Unsloth Colab (Qwen3.5 0.8B)

```python
from datasets import load_dataset
import json

ds = load_dataset("KEVIN_HF_USERNAME/toti-cakery-toolcall")  # 3 splits

def to_text(ex):
    msgs = ex["messages"]
    for m in msgs:
        for tc in (m.get("tool_calls") or []):
            if isinstance(tc["function"]["arguments"], str):
                tc["function"]["arguments"] = json.loads(tc["function"]["arguments"])
    return {"text": tokenizer.apply_chat_template(
        msgs, tools=json.loads(ex["tools_json"]),
        tokenize=False, add_generation_prompt=False)}

ds = ds.map(to_text)
print(ds["train"][0]["text"][:2000])  # sanity: <tools> block + <tool_call> render
```

Training notes:

- Pass `eval_dataset=ds["validation"]` to `SFTTrainer` and watch val-loss
  (rising val-loss while train-loss falls = overfitting → stop earlier).
- Use `train_on_responses_only` (Unsloth util) with the Qwen3.5
  instruction/response markers so the large repeated system prompt is masked
  out of the loss.
- Suggested start: LoRA r=16, alpha=16, lr=2e-4, 2-3 epochs, effective batch 8-16.

## After training: export + measure

1. Export GGUF from Unsloth, create the Ollama model (**same chat template as
   the base model** — a mismatched template is the #1 cause of "worse after
   export"), e.g. `ollama create toti-qwen -f Modelfile`.
2. Run the functional eval harness (BFCL-style) on the held-out test split
   against the REAL serving path (repo `finetune/eval_tool_calling.py`):

```bash
python finetune/eval_tool_calling.py --model qwen3.5:0.8b   # baseline
python finetune/eval_tool_calling.py --model toti-qwen      # fine-tuned
```

Metrics reported: function-selection accuracy, parameter exact-match,
invalid-call rate, irrelevance detection (knowing when NOT to call a tool),
false-tool-call rate — per category and aggregate. Compare the two JSON
result files; that comparison (not training loss) is the verdict on whether
the fine-tune worked. Then point the chatbot's `.env` `LLM_MODEL` at the new
model.

## Provenance

Generated deterministically (seed 42) by `finetune/generate_dataset.py` in the
project repo — templates + slot-filling over the real shop menu; no LLM was
used to synthesize rows. Independently audited (structure, behavior,
statistics, leakage) before release.
