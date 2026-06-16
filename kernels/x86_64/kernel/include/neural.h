/* Neural backend ABI (subset of kernel_spec/subsystems/slm.md:455-481).
 *
 * The in-kernel neural backend loads a llama2.c-style flat model passed as a
 * boot module and runs a freestanding transformer forward pass. Until the
 * Stage 2 implementation lands, slm_neural_load_model returns -1 so backend
 * selection falls back to the rule engine. */
#ifndef AUTON_NEURAL_H
#define AUTON_NEURAL_H

#include <stdint.h>

/* Model on-disk formats. AUTON is our own llama2.c-style flat format (we own
 * both the host exporter and the kernel loader); GGUF/ONNX stay roadmap. */
typedef enum model_format {
	MODEL_FORMAT_GGUF = 0,
	MODEL_FORMAT_ONNX = 1,
	MODEL_FORMAT_AUTON = 2,
} model_format_t;

/* Sampling configuration for one generation. */
typedef struct inference_config {
	float    temperature;   /* 0.0 = greedy */
	float    top_p;
	uint32_t max_tokens;
	int      greedy;
} inference_config_t;

/* Load a model previously placed in memory (a boot module). Parses the flat
 * header and maps tensors. Returns 0 on success, negative on failure. */
int slm_neural_load_model(const void *model_data, uint64_t model_size,
			  model_format_t format);

/* 1 if a model is loaded and the neural backend is usable. */
int slm_neural_available(void);

/* Tokenize text into model token ids. Returns token count. */
uint32_t slm_neural_tokenize(const char *text, uint32_t text_len,
			     uint32_t *token_ids, uint32_t max_tokens);

/* Decode token ids back to text. Returns string length. */
uint32_t slm_neural_detokenize(const uint32_t *token_ids, uint32_t token_count,
			       char *text_buf, uint32_t buf_size);

/* Run inference: given input tokens, generate output tokens. Returns count. */
uint32_t slm_neural_infer(const uint32_t *input_tokens, uint32_t input_len,
			  uint32_t *output_tokens, uint32_t max_output,
			  const inference_config_t *config);

/* Reset the KV cache (start a fresh context). */
void slm_neural_reset_cache(void);

/* Write a short model-info string ("auton-slm-tiny (10M, int8) 11 MB"). */
void slm_neural_model_info(char *buf, uint32_t buf_size);

#endif /* AUTON_NEURAL_H */
