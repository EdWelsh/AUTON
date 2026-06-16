/* Neural backend — Phase B stub.
 *
 * Backend selection (slm_init) calls slm_neural_load_model; returning -1 here
 * makes it fall back to the rule engine. The real freestanding transformer
 * (loader, tokenizer, quantized matmul, forward pass) replaces this file's
 * contents in Stage 2 (plan Phases C-F). Kept as a separate translation unit
 * so the float-using neural code can later be compiled with SSE while the rest
 * of the kernel stays integer-only. */
#include "neural.h"

int slm_neural_load_model(const void *model_data, uint64_t model_size,
			  model_format_t format)
{
	(void)model_data;
	(void)model_size;
	(void)format;
	return -1;                      /* not implemented yet -> rule engine */
}

int slm_neural_available(void)
{
	return 0;
}

uint32_t slm_neural_tokenize(const char *text, uint32_t text_len,
			     uint32_t *token_ids, uint32_t max_tokens)
{
	(void)text;
	(void)text_len;
	(void)token_ids;
	(void)max_tokens;
	return 0;
}

uint32_t slm_neural_detokenize(const uint32_t *token_ids, uint32_t token_count,
			       char *text_buf, uint32_t buf_size)
{
	(void)token_ids;
	(void)token_count;
	if (buf_size)
		text_buf[0] = '\0';
	return 0;
}

uint32_t slm_neural_infer(const uint32_t *input_tokens, uint32_t input_len,
			  uint32_t *output_tokens, uint32_t max_output,
			  const inference_config_t *config)
{
	(void)input_tokens;
	(void)input_len;
	(void)output_tokens;
	(void)max_output;
	(void)config;
	return 0;
}

void slm_neural_reset_cache(void)
{
}

void slm_neural_model_info(char *buf, uint32_t buf_size)
{
	const char *s = "none";
	uint32_t i = 0;
	for (; s[i] && i < buf_size - 1; i++)
		buf[i] = s[i];
	if (buf_size)
		buf[i] = '\0';
}
