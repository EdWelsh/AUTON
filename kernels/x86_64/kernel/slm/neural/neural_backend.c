/* In-kernel neural backend: loads the AUTON flat model from a boot module and
 * runs a freestanding fp32 transformer forward pass (RMSNorm, RoPE, GQA
 * attention with a KV cache, SwiGLU FFN). Implements the slm_neural_* ABI.
 *
 * Float-only; compiled with SSE (see toolchain.mk). The forward pass mirrors
 * SLM/model/transformer.py: NeoX-style RoPE (rotate_half on concatenated
 * halves) and weight-tied logits. fp32 keeps the first cut correct and simple;
 * int8 quantization (acceptance crit #15) is a documented extension.
 *
 * Flat layout is the contract in SLM/tools/auton_format.py. */
#include "neural.h"
#include "kmath.h"
#include "phys.h"
#include "kernel.h"

#define MAGIC      0x4E4F5455u          /* "UTON" little-endian */
#define VERSION    1u
#define MAX_LAYERS 16
#define MAX_CTX    256                  /* cap context to bound KV-cache size */
#define MAX_TOKENS 64

struct flat_header {
	uint32_t magic, version, dim, hidden_dim, n_layers, n_heads, n_kv_heads,
		 vocab_size, seq_len, quant;
};

struct model {
	uint32_t dim, hidden_dim, n_layers, n_heads, n_kv_heads, vocab_size;
	uint32_t seq_len, head_dim, kv_dim;

	const float *token_emb;                 /* [vocab, dim] (also lm_head, tied) */
	const float *rms_att[MAX_LAYERS];       /* [dim] */
	const float *wq[MAX_LAYERS];            /* [n_heads*head_dim, dim] */
	const float *wk[MAX_LAYERS];            /* [kv_dim, dim] */
	const float *wv[MAX_LAYERS];            /* [kv_dim, dim] */
	const float *wo[MAX_LAYERS];            /* [dim, n_heads*head_dim] */
	const float *rms_ffn[MAX_LAYERS];       /* [dim] */
	const float *w1[MAX_LAYERS];            /* gate [hidden, dim] */
	const float *w2[MAX_LAYERS];            /* down [dim, hidden] */
	const float *w3[MAX_LAYERS];            /* up   [hidden, dim] */
	const float *rms_final;                 /* [dim] */

	/* Tokenizer: id -> string, in a contiguous block. */
	const char *vocab[MODEL_MAX_VOCAB_CAP];
	uint8_t     vocab_len[MODEL_MAX_VOCAB_CAP];

	/* Runtime scratch (from the DMA arena). */
	float *x, *xb, *xb2, *hb, *hb2, *q, *att, *logits;
	float *key_cache, *value_cache;         /* [layer * ctx * kv_dim] */
	uint32_t ctx;                           /* effective context cap */
	uint32_t pos;                           /* current KV position */
	int loaded;
};

static struct model M;

/* Consume 'count' floats from the cursor, returning the pointer and advancing. */
static const float *take(const float **cur, uint32_t count)
{
	const float *p = *cur;
	*cur += count;
	return p;
}

int slm_neural_load_model(const void *data, uint64_t size, model_format_t fmt)
{
	if (fmt != MODEL_FORMAT_AUTON || !data || size < sizeof(struct flat_header))
		return -1;

	const struct flat_header *h = (const struct flat_header *)data;
	if (h->magic != MAGIC || h->version != VERSION || h->quant != 0)
		return -1;
	if (h->n_layers > MAX_LAYERS || h->n_heads == 0 ||
	    h->n_kv_heads == 0 || h->n_heads % h->n_kv_heads != 0 ||
	    h->vocab_size > MODEL_MAX_VOCAB_CAP || (h->dim % h->n_heads) != 0)
		return -1;

	M.dim = h->dim;
	M.hidden_dim = h->hidden_dim;
	M.n_layers = h->n_layers;
	M.n_heads = h->n_heads;
	M.n_kv_heads = h->n_kv_heads;
	M.vocab_size = h->vocab_size;
	M.seq_len = h->seq_len;
	M.head_dim = h->dim / h->n_heads;
	M.kv_dim = M.head_dim * h->n_kv_heads;

	const float *cur = (const float *)((const uint8_t *)data + sizeof(*h));
	uint32_t hd = M.head_dim;

	/* Tensors are interleaved per layer in the file (matching the exporter),
	 * so read them in that order, not grouped by kind. */
	M.token_emb = take(&cur, M.vocab_size * M.dim);
	for (uint32_t l = 0; l < M.n_layers; l++) {
		M.rms_att[l] = take(&cur, M.dim);
		M.wq[l]      = take(&cur, M.n_heads * hd * M.dim);
		M.wk[l]      = take(&cur, M.n_kv_heads * hd * M.dim);
		M.wv[l]      = take(&cur, M.n_kv_heads * hd * M.dim);
		M.wo[l]      = take(&cur, M.dim * M.n_heads * hd);
		M.rms_ffn[l] = take(&cur, M.dim);
		M.w1[l]      = take(&cur, M.hidden_dim * M.dim);
		M.w2[l]      = take(&cur, M.dim * M.hidden_dim);
		M.w3[l]      = take(&cur, M.hidden_dim * M.dim);
	}
	M.rms_final = take(&cur, M.dim);

	/* Tokenizer block: max_token_len (u32), then per token { score f32,
	 * len u32, bytes }. */
	const uint8_t *t = (const uint8_t *)cur;
	const uint8_t *end = (const uint8_t *)data + size;
	t += 4;                                 /* skip max_token_len */
	for (uint32_t i = 0; i < M.vocab_size; i++) {
		if (t + 8 > end)
			return -1;
		t += 4;                         /* skip score */
		uint32_t len;
		__builtin_memcpy(&len, t, 4);
		t += 4;
		if (t + len > end || len > 255)
			return -1;
		M.vocab[i] = (const char *)t;
		M.vocab_len[i] = (uint8_t)len;
		t += len;
	}

	/* Allocate runtime buffers. Cap context to bound the KV cache. */
	M.ctx = M.seq_len < MAX_CTX ? M.seq_len : MAX_CTX;
	uint32_t nh_hd = M.n_heads * hd;
	M.x = dma_alloc(M.dim * 4, 16);
	M.xb = dma_alloc(M.dim * 4, 16);
	M.xb2 = dma_alloc(M.dim * 4, 16);
	M.hb = dma_alloc(M.hidden_dim * 4, 16);
	M.hb2 = dma_alloc(M.hidden_dim * 4, 16);
	M.q = dma_alloc(nh_hd * 4, 16);
	M.att = dma_alloc(M.ctx * 4, 16);
	M.logits = dma_alloc(M.vocab_size * 4, 16);
	M.key_cache = dma_alloc((uint64_t)M.n_layers * M.ctx * M.kv_dim * 4, 16);
	M.value_cache = dma_alloc((uint64_t)M.n_layers * M.ctx * M.kv_dim * 4, 16);
	if (!M.x || !M.logits || !M.key_cache || !M.value_cache)
		return -1;

	M.pos = 0;
	M.loaded = 1;
	return 0;
}

int slm_neural_available(void)
{
	return M.loaded;
}

void slm_neural_reset_cache(void)
{
	M.pos = 0;
}

/* y[out] = W[out,in] @ x[in], W row-major. */
static void matmul(float *y, const float *x, const float *W,
		   uint32_t in, uint32_t out)
{
	for (uint32_t o = 0; o < out; o++) {
		const float *row = W + (uint64_t)o * in;
		float sum = 0.0f;
		for (uint32_t i = 0; i < in; i++)
			sum += row[i] * x[i];
		y[o] = sum;
	}
}

static void rmsnorm(float *o, const float *x, const float *w, uint32_t n)
{
	float ss = 0.0f;
	for (uint32_t i = 0; i < n; i++)
		ss += x[i] * x[i];
	ss = 1.0f / ksqrtf(ss / (float)n + 1e-6f);
	for (uint32_t i = 0; i < n; i++)
		o[i] = x[i] * ss * w[i];
}

static void softmax(float *x, uint32_t n)
{
	float mx = x[0];
	for (uint32_t i = 1; i < n; i++)
		if (x[i] > mx)
			mx = x[i];
	float sum = 0.0f;
	for (uint32_t i = 0; i < n; i++) {
		x[i] = kexpf(x[i] - mx);
		sum += x[i];
	}
	for (uint32_t i = 0; i < n; i++)
		x[i] /= sum;
}

/* NeoX-style RoPE on a [n_heads x head_dim] vector at absolute position pos. */
static void rope(float *vec, uint32_t n_heads, uint32_t hd, uint32_t pos)
{
	uint32_t half = hd / 2;
	for (uint32_t h = 0; h < n_heads; h++) {
		float *v = vec + h * hd;
		for (uint32_t j = 0; j < half; j++) {
			float freq = 1.0f;
			/* theta^(2j/hd): compute as exp(-(2j/hd)*ln(theta)). */
			float exponent = (float)(2 * j) / (float)hd;
			freq = kexpf(-exponent * 9.21034037f);  /* ln(10000) */
			float ang = (float)pos * freq;
			float c = kcosf(ang), s = ksinf(ang);
			float a = v[j], b = v[j + half];
			v[j] = a * c - b * s;
			v[j + half] = b * c + a * s;
		}
	}
}

/* One decoder step for token 'tok' at position 'pos'; fills M.logits. */
static void forward(uint32_t tok, uint32_t pos)
{
	uint32_t dim = M.dim, hd = M.head_dim, kvd = M.kv_dim;
	uint32_t n_rep = M.n_heads / M.n_kv_heads;
	float scale = 1.0f / ksqrtf((float)hd);

	__builtin_memcpy(M.x, M.token_emb + (uint64_t)tok * dim, dim * 4);

	for (uint32_t l = 0; l < M.n_layers; l++) {
		rmsnorm(M.xb, M.x, M.rms_att[l], dim);

		float *krow = M.key_cache + ((uint64_t)l * M.ctx + pos) * kvd;
		float *vrow = M.value_cache + ((uint64_t)l * M.ctx + pos) * kvd;
		matmul(M.q, M.xb, M.wq[l], dim, M.n_heads * hd);
		matmul(krow, M.xb, M.wk[l], dim, kvd);
		matmul(vrow, M.xb, M.wv[l], dim, kvd);

		rope(M.q, M.n_heads, hd, pos);
		rope(krow, M.n_kv_heads, hd, pos);

		/* GQA attention per query head into M.xb (reused as attn output). */
		for (uint32_t h = 0; h < M.n_heads; h++) {
			float *qh = M.q + h * hd;
			uint32_t kvh = h / n_rep;
			for (uint32_t p = 0; p <= pos; p++) {
				const float *kh = M.key_cache +
					((uint64_t)l * M.ctx + p) * kvd + kvh * hd;
				float dot = 0.0f;
				for (uint32_t i = 0; i < hd; i++)
					dot += qh[i] * kh[i];
				M.att[p] = dot * scale;
			}
			softmax(M.att, pos + 1);
			float *out = M.xb + h * hd;
			for (uint32_t i = 0; i < hd; i++)
				out[i] = 0.0f;
			for (uint32_t p = 0; p <= pos; p++) {
				const float *vh = M.value_cache +
					((uint64_t)l * M.ctx + p) * kvd + kvh * hd;
				float a = M.att[p];
				for (uint32_t i = 0; i < hd; i++)
					out[i] += a * vh[i];
			}
		}

		matmul(M.xb2, M.xb, M.wo[l], M.n_heads * hd, dim);
		for (uint32_t i = 0; i < dim; i++)
			M.x[i] += M.xb2[i];

		/* SwiGLU FFN. */
		rmsnorm(M.xb, M.x, M.rms_ffn[l], dim);
		matmul(M.hb, M.xb, M.w1[l], dim, M.hidden_dim);
		matmul(M.hb2, M.xb, M.w3[l], dim, M.hidden_dim);
		for (uint32_t i = 0; i < M.hidden_dim; i++) {
			float v = M.hb[i];
			v = v / (1.0f + kexpf(-v));     /* SiLU */
			M.hb[i] = v * M.hb2[i];
		}
		matmul(M.xb2, M.hb, M.w2[l], M.hidden_dim, dim);
		for (uint32_t i = 0; i < dim; i++)
			M.x[i] += M.xb2[i];
	}

	rmsnorm(M.x, M.x, M.rms_final, dim);
	matmul(M.logits, M.x, M.token_emb, dim, M.vocab_size);  /* tied lm_head */
}

uint32_t slm_neural_tokenize(const char *text, uint32_t text_len,
			     uint32_t *ids, uint32_t max_tokens)
{
	/* Word-level: split on whitespace, match the vocab, else <unk> (id 1). */
	uint32_t n = 0, i = 0;
	while (i < text_len && n < max_tokens) {
		while (i < text_len && text[i] == ' ')
			i++;
		uint32_t start = i;
		while (i < text_len && text[i] != ' ')
			i++;
		uint32_t len = i - start;
		if (len == 0)
			break;
		uint32_t id = 1;                /* <unk> */
		for (uint32_t v = 0; v < M.vocab_size; v++) {
			if (M.vocab_len[v] != len)
				continue;
			uint32_t k = 0;
			while (k < len && M.vocab[v][k] == text[start + k])
				k++;
			if (k == len) {
				id = v;
				break;
			}
		}
		ids[n++] = id;
	}
	return n;
}

uint32_t slm_neural_detokenize(const uint32_t *ids, uint32_t count,
			       char *buf, uint32_t buf_size)
{
	uint32_t p = 0;
	for (uint32_t i = 0; i < count; i++) {
		uint32_t id = ids[i];
		if (id >= M.vocab_size)
			continue;
		if (p && p < buf_size - 1)
			buf[p++] = ' ';
		uint8_t len = M.vocab_len[id];
		for (uint8_t k = 0; k < len && p < buf_size - 1; k++)
			buf[p++] = M.vocab[id][k];
	}
	if (buf_size)
		buf[p] = '\0';
	return p;
}

static uint32_t argmax(const float *v, uint32_t n)
{
	uint32_t best = 0;
	for (uint32_t i = 1; i < n; i++)
		if (v[i] > v[best])
			best = i;
	return best;
}

uint32_t slm_neural_infer(const uint32_t *input, uint32_t input_len,
			  uint32_t *output, uint32_t max_output,
			  const inference_config_t *cfg)
{
	(void)cfg;
	if (!M.loaded || input_len == 0)
		return 0;

	slm_neural_reset_cache();
	uint32_t pos = 0;

	/* Ingest the prompt; keep the last logits to seed generation. */
	for (uint32_t i = 0; i < input_len && pos < M.ctx - 1; i++, pos++)
		forward(input[i], pos);

	uint32_t n = 0;
	uint32_t next = argmax(M.logits, M.vocab_size);
	while (n < max_output && pos < M.ctx - 1) {
		if (next == 3 /* <eos> */ || next == 0 /* <pad> */)
			break;
		output[n++] = next;
		forward(next, pos);
		pos++;
		next = argmax(M.logits, M.vocab_size);
	}
	return n;
}

void slm_neural_model_info(char *buf, uint32_t buf_size)
{
	/* "auton-slm-tiny (Nd/LL) fp32" — keep it short. */
	const char *s = M.loaded ? "auton-slm (fp32)" : "none";
	uint32_t i = 0;
	for (; s[i] && i < buf_size - 1; i++)
		buf[i] = s[i];
	if (buf_size)
		buf[i] = '\0';
}
