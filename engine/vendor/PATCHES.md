# Vendored Ming-3.0-tts

Source: https://github.com/inclusionAI/Ming-3.0-tts (MIT, see `ming/LICENSE`).
Only the runtime modules needed for the 0.5B model are included.

Local changes (search for "Timbre patch"):

- `modeling_bailingmm.py`: the three `torch.autocast(device_type='cuda', dtype=torch.bfloat16)`
  blocks now use `self._autocast()`, which follows the model's device and dtype, so the
  model runs on CUDA, ROCm, Intel XPU and CPU, and in bf16, fp16 or fp32.
  `encode_prompt_latent` casts to the model dtype instead of hard-coded bf16.
- `ming_tts.py`: `MingTTS.__init__` accepts `dtype` and `local_files_only`.
