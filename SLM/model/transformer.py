"""A compact decoder-only transformer (RMSNorm + RoPE + GQA + SwiGLU).

This is a real, trainable PyTorch implementation parameterized by
:class:`~model.config.ModelConfig`. It is deliberately small and dependency-light
(torch only) so the tiny configs train end-to-end on CPU in seconds, while still
exercising the same architecture the larger configs describe.
"""

from __future__ import annotations

import torch
import torch.nn as nn
import torch.nn.functional as F

from model.config import ModelConfig


class RMSNorm(nn.Module):
    """Root-mean-square layer normalization (no bias, no mean subtraction)."""

    def __init__(self, dim: int, eps: float = 1e-6) -> None:
        super().__init__()
        self.eps = eps
        self.weight = nn.Parameter(torch.ones(dim))

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        norm = x * torch.rsqrt(x.pow(2).mean(-1, keepdim=True) + self.eps)
        return norm * self.weight


def build_rope_cache(seq_len: int, head_dim: int, theta: float, device, dtype):
    """Precompute rotary (cos, sin) tables of shape ``(seq_len, head_dim)``."""
    inv_freq = 1.0 / (theta ** (torch.arange(0, head_dim, 2, device=device).float() / head_dim))
    pos = torch.arange(seq_len, device=device).float()
    freqs = torch.outer(pos, inv_freq)  # (seq_len, head_dim/2)
    emb = torch.cat((freqs, freqs), dim=-1)  # (seq_len, head_dim)
    return emb.cos().to(dtype), emb.sin().to(dtype)


def _rotate_half(x: torch.Tensor) -> torch.Tensor:
    half = x.shape[-1] // 2
    x1, x2 = x[..., :half], x[..., half:]
    return torch.cat((-x2, x1), dim=-1)


def apply_rope(x: torch.Tensor, cos: torch.Tensor, sin: torch.Tensor) -> torch.Tensor:
    """Apply rotary embeddings to ``x`` of shape ``(B, n_heads, T, head_dim)``."""
    cos = cos.unsqueeze(0).unsqueeze(0)
    sin = sin.unsqueeze(0).unsqueeze(0)
    return x * cos + _rotate_half(x) * sin


class Attention(nn.Module):
    """Grouped-query causal self-attention with rotary position embeddings."""

    def __init__(self, cfg: ModelConfig) -> None:
        super().__init__()
        self.n_heads = cfg.num_attention_heads
        self.n_kv_heads = cfg.num_key_value_heads
        self.head_dim = cfg.head_dim
        self.n_rep = self.n_heads // self.n_kv_heads
        self.dropout = cfg.attention_dropout

        self.q_proj = nn.Linear(cfg.hidden_size, self.n_heads * self.head_dim, bias=False)
        self.k_proj = nn.Linear(cfg.hidden_size, self.n_kv_heads * self.head_dim, bias=False)
        self.v_proj = nn.Linear(cfg.hidden_size, self.n_kv_heads * self.head_dim, bias=False)
        self.o_proj = nn.Linear(self.n_heads * self.head_dim, cfg.hidden_size, bias=False)

    def forward(self, x: torch.Tensor, cos: torch.Tensor, sin: torch.Tensor) -> torch.Tensor:
        b, t, _ = x.shape
        q = self.q_proj(x).view(b, t, self.n_heads, self.head_dim).transpose(1, 2)
        k = self.k_proj(x).view(b, t, self.n_kv_heads, self.head_dim).transpose(1, 2)
        v = self.v_proj(x).view(b, t, self.n_kv_heads, self.head_dim).transpose(1, 2)

        q = apply_rope(q, cos[:t], sin[:t])
        k = apply_rope(k, cos[:t], sin[:t])

        # Expand KV heads to match Q heads (grouped-query attention).
        k = k.repeat_interleave(self.n_rep, dim=1)
        v = v.repeat_interleave(self.n_rep, dim=1)

        attn = F.scaled_dot_product_attention(
            q, k, v, is_causal=True, dropout_p=self.dropout if self.training else 0.0
        )
        attn = attn.transpose(1, 2).contiguous().view(b, t, -1)
        return self.o_proj(attn)


class SwiGLU(nn.Module):
    """SwiGLU feed-forward network: ``down(silu(gate(x)) * up(x))``."""

    def __init__(self, cfg: ModelConfig) -> None:
        super().__init__()
        self.gate_proj = nn.Linear(cfg.hidden_size, cfg.intermediate_size, bias=False)
        self.up_proj = nn.Linear(cfg.hidden_size, cfg.intermediate_size, bias=False)
        self.down_proj = nn.Linear(cfg.intermediate_size, cfg.hidden_size, bias=False)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.down_proj(F.silu(self.gate_proj(x)) * self.up_proj(x))


class Block(nn.Module):
    def __init__(self, cfg: ModelConfig) -> None:
        super().__init__()
        self.attn_norm = RMSNorm(cfg.hidden_size)
        self.attn = Attention(cfg)
        self.ffn_norm = RMSNorm(cfg.hidden_size)
        self.ffn = SwiGLU(cfg)
        self.dropout = nn.Dropout(cfg.hidden_dropout)

    def forward(self, x: torch.Tensor, cos: torch.Tensor, sin: torch.Tensor) -> torch.Tensor:
        x = x + self.dropout(self.attn(self.attn_norm(x), cos, sin))
        x = x + self.dropout(self.ffn(self.ffn_norm(x)))
        return x


class SLMTransformer(nn.Module):
    """Decoder-only language model with tied input/output embeddings."""

    def __init__(self, cfg: ModelConfig) -> None:
        super().__init__()
        self.cfg = cfg
        self.embed_tokens = nn.Embedding(cfg.vocab_size, cfg.hidden_size)
        self.layers = nn.ModuleList(Block(cfg) for _ in range(cfg.num_layers))
        self.norm = RMSNorm(cfg.hidden_size)
        self.lm_head = nn.Linear(cfg.hidden_size, cfg.vocab_size, bias=False)
        self.lm_head.weight = self.embed_tokens.weight  # weight tying

    def num_parameters(self) -> int:
        # Tied head shares the embedding weight; count unique parameters.
        seen: set[int] = set()
        total = 0
        for p in self.parameters():
            if id(p) in seen:
                continue
            seen.add(id(p))
            total += p.numel()
        return total

    def forward(self, input_ids: torch.Tensor, labels: torch.Tensor | None = None):
        b, t = input_ids.shape
        x = self.embed_tokens(input_ids)
        cos, sin = build_rope_cache(t, self.cfg.head_dim, self.cfg.rope_theta, x.device, x.dtype)
        for layer in self.layers:
            x = layer(x, cos, sin)
        x = self.norm(x)
        logits = self.lm_head(x)

        loss = None
        if labels is not None:
            loss = F.cross_entropy(
                logits[:, :-1].reshape(-1, logits.size(-1)),
                labels[:, 1:].reshape(-1),
                ignore_index=-100,
            )
        return logits, loss
