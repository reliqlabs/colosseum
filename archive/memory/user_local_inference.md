---
name: Local inference context preference
description: User runs local LLMs (LM Studio, MLX/GGUF) at the model's maximum context length by default — KV cache sizing dominates memory math
type: user
originSessionId: 58c6368a-7b86-40a9-a8cc-b4091a61c61f
---
User sets context length to the model maximum when running local LLMs (LM Studio, MLX and GGUF). This means KV cache is often the dominant memory consumer, not weights — at 128k–256k context, KV can hit 40–60GB on 30B–70B-class models.

When advising on local inference setup (quantization choices, model selection, memory budgeting), assume max-context usage and size KV cache accordingly. Recommend KV cache quantization (Q8_0) + Flash Attention by default for this user's workflow, even though it's not necessary for typical short-context use.
