---
name: Local model speed preference
description: User prioritizes inference speed over single-shot quality for local models — dense models get under-used in practice even when higher quality
type: feedback
originSessionId: 58c6368a-7b86-40a9-a8cc-b4091a61c61f
---
For local model selection, user prefers fast MoE models over slower dense models even when the dense model has a quality advantage. Observed: dense Q8 GGUF models (e.g., Qwen3.6 27B) get under-used in practice because they're noticeably slower than MoE alternatives (e.g., Gemma 4 26B A4B with 4B active).

**Why:** A quality advantage that isn't actually reached for because of latency is a theoretical advantage. Real-world utility = quality × actually-used-frequency.

**How to apply:** When recommending local models for this user, weight active-param count and runtime format (MLX > GGUF on Apple Silicon) heavily. Don't push dense models on "quality ceiling" grounds alone — verify the user will actually tolerate the speed. Prefer MoE with small active params (sub-10B active) and MLX format unless there's a strong reason otherwise.
