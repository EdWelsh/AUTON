# Data Preparation Specification

## Objective

Prepare high-quality tokenized datasets for training Small Language Models (SLMs) that will power the AUTON kernel's natural language interface.

## Dataset Requirements

### Target Corpus Size

| Model Size | Tokens Required | Raw Text (approx) | Dataset Size (tokenized) |
|-----------|-----------------|-------------------|-------------------------|
| Tiny (10M) | 100M-500M | 500MB-2GB | 200MB-1GB |
| Small (50M) | 500M-2B | 2GB-8GB | 1GB-4GB |
| Medium (150M) | 2B-10B | 8GB-40GB | 4GB-20GB |
| Large (500M) | 10B-50B | 40GB-200GB | 20GB-100GB |

### Data Sources

**1. Operating System Code (40%)**
- Linux kernel source (drivers, core, arch, mm, fs)
- FreeBSD kernel source
- Driver documentation and comments
- System call man pages
- Kernel boot messages

**2. Hardware Documentation (30%)**
- PCI ID database (pci.ids)
- USB ID database (usb.ids)
- Device datasheets (Intel, AMD, ARM, RISC-V)
- ACPI specifications
- Device Tree descriptions
- Hardware architecture manuals (Intel SDM, ARM ARM)

**3. System Administration (20%)**
- Command man pages (bash, coreutils, systemd)
- Configuration file documentation
- Package manager guides (apt, yum, pacman)
- System logs (dmesg, syslog examples)
- Installation guides

**4. Natural Language Queries (10%)**
- Stack Overflow Q&A (hardware, drivers, kernel)
- Reddit r/linuxquestions, r/archlinux
- Forum posts about hardware issues
- Troubleshooting guides

### Data Quality Criteria

**Inclusion criteria:**
✅ Technical accuracy
✅ Relevant to OS/hardware/drivers
✅ Clear, well-structured text
✅ English language (primary)
✅ Recent (prefer last 5 years)

**Exclusion criteria:**
❌ Non-technical content
❌ Spam or low-quality posts
❌ Non-English (for now)
❌ Duplicate content
❌ Offensive or inappropriate content

## Data Collection

### Automated Collection

Use web scraping and API access for:
- GitHub repositories (kernel sources)
- Documentation sites (kernel.org, wiki.archlinux.org)
- Man pages (man7.org)
- Hardware vendor sites

### Manual Curation

For high-value datasets:
- PCI/USB ID databases (curated lists)
- Datasheets (PDF to text extraction)
- Architecture manuals (extract relevant sections)

### Storage

Raw collected data stored in:
```
SLM/datasets/raw/
├── kernel_sources.txt
├── hardware_docs.txt
├── sysadmin_guides.txt
├── qa_forums.txt
└── pci_usb_ids.txt
```

## Data Cleaning

### Cleaning Pipeline

**Step 1: Deduplication**
- Remove exact duplicates (hash-based)
- Remove near-duplicates (MinHash/LSH)
- Target: < 5% duplication rate

**Step 2: Filtering**
- Remove non-text content (binary, base64)
- Remove excessively short documents (< 50 chars)
- Remove excessively long documents (> 100K chars)
- Filter by language (detect non-English, remove if > 20%)

**Step 3: Normalization**
- Normalize whitespace (tabs → spaces, multiple spaces → single)
- Fix encoding issues (UTF-8 validation)
- Remove control characters
- Normalize line endings (CRLF → LF)

**Step 4: Quality Scoring**
- Compute readability metrics
- Check technical term frequency
- Filter low-quality documents (threshold: bottom 10%)

### Cleaning Script

Implementation in `SLM/tools/dataset_builder.py`:

```python
def clean_dataset(input_path, output_path):
    # Load raw text
    with open(input_path) as f:
        docs = f.read().split("\n\n")

    # Deduplicate
    docs = deduplicate(docs)

    # Filter
    docs = [d for d in docs if is_valid_doc(d)]

    # Normalize
    docs = [normalize_text(d) for d in docs]

    # Quality score and filter
    docs = [(d, quality_score(d)) for d in docs]
    docs = [d for d, score in docs if score > threshold]

    # Save cleaned
    with open(output_path, 'w') as f:
        f.write("\n\n".join(docs))
```

## Tokenization

### Tokenizer Selection

**Recommended: BPE (Byte-Pair Encoding)**
- Good compression for technical text
- Handles rare words well (subword units)
- Used by GPT models

**Alternative: WordPiece**
- Similar to BPE
- Used by BERT models

**Alternative: SentencePiece**
- Language-agnostic
- Treats text as raw bytes

### Vocabulary Size

| Model Size | Vocab Size | Rationale |
|-----------|------------|-----------|
| Tiny | 16,000 | Fewer tokens, smaller embedding table |
| Small | 32,000 | Good balance for technical text |
| Medium | 32,000 | Standard GPT-2 size |
| Large | 32,000 | Same as medium (diminishing returns) |

### Training Tokenizer

Use `tokenizers` library (HuggingFace):

```python
from tokenizers import Tokenizer, models, trainers, pre_tokenizers

# Initialize BPE tokenizer
tokenizer = Tokenizer(models.BPE())
tokenizer.pre_tokenizer = pre_tokenizers.ByteLevel(add_prefix_space=False)

# Train on cleaned corpus
trainer = trainers.BpeTrainer(
    vocab_size=32000,
    min_frequency=2,
    special_tokens=["<|endoftext|>", "<|pad|>", "<|unk|>"],
)
tokenizer.train(files=["SLM/datasets/raw/cleaned.txt"], trainer=trainer)

# Save tokenizer
tokenizer.save("SLM/datasets/processed/tokenizer.json")
```

### Tokenization Pipeline

**Step 1: Load tokenizer**
```python
from tokenizers import Tokenizer
tokenizer = Tokenizer.from_file("tokenizer.json")
```

**Step 2: Tokenize documents**
```python
def tokenize_dataset(input_path, output_path, tokenizer):
    with open(input_path) as f:
        text = f.read()

    # Tokenize
    encoded = tokenizer.encode(text)
    token_ids = encoded.ids

    # Save as binary (numpy array)
    import numpy as np
    np.array(token_ids, dtype=np.uint16).tofile(output_path)
```

**Step 3: Create train/val/test splits**
```python
# 90% train, 5% val, 5% test
train_size = int(len(token_ids) * 0.9)
val_size = int(len(token_ids) * 0.05)

train_tokens = token_ids[:train_size]
val_tokens = token_ids[train_size:train_size+val_size]
test_tokens = token_ids[train_size+val_size:]

# Save splits
np.array(train_tokens, dtype=np.uint16).tofile("train.bin")
np.array(val_tokens, dtype=np.uint16).tofile("val.bin")
np.array(test_tokens, dtype=np.uint16).tofile("test.bin")
```

## Validation

### Dataset Statistics

Compute and log:
- Total tokens: `len(token_ids)`
- Vocabulary coverage: `len(set(token_ids)) / vocab_size`
- Average token length: `mean([len(tokenizer.decode([t])) for t in unique_tokens])`
- Compression ratio: `len(raw_text_bytes) / (len(token_ids) * 2)`

### Quality Checks

**1. Vocabulary Coverage**
- Should be > 80% of vocab used
- If < 50%, vocabulary is too large or dataset too small

**2. Token Distribution**
- Plot token frequency distribution
- Should follow power law (Zipf's law)
- Rare tokens (< 10 occurrences) should be < 20% of vocab

**3. Sample Decoding**
- Decode random 100-token sequences
- Verify: coherent text, no excessive special tokens, proper technical terms

### Acceptance Criteria

A dataset is accepted if:
✅ Total tokens meet minimum (see table above)
✅ Vocabulary coverage > 80%
✅ Compression ratio 3-5x
✅ Sample decodings are coherent
✅ No encoding errors (all tokens decodable)
✅ Train/val/test splits created successfully

## Exploratory Data Analysis

### Jupyter Notebooks

Use `SLM/notebooks/01_data_exploration.ipynb` for:
- Token distribution plots
- Vocabulary coverage analysis
- Sample generations
- Rare token inspection
- Domain-specific term frequency

### Visualization

```python
import matplotlib.pyplot as plt
import numpy as np

# Token frequency
token_counts = Counter(token_ids)
freqs = sorted(token_counts.values(), reverse=True)
plt.plot(np.log(freqs))
plt.xlabel("Token rank (log)")
plt.ylabel("Frequency (log)")
plt.title("Token Frequency Distribution (Zipf's Law)")
```

## Agent Tools

DataScientistAgent has access to:

**`analyze_dataset(dataset_path, output_path)`**
- Computes statistics (vocab size, token count, coverage)
- Generates report JSON

**`tokenize_data(input_path, output_path, vocab_size, tokenizer_type)`**
- Trains tokenizer on cleaned corpus
- Tokenizes and creates train/val/test splits

**`run_notebook(notebook_path, timeout)`**
- Executes Jupyter notebook for EDA
- Returns rendered output

## Output Artifacts

After data preparation, the following must exist:

```
SLM/datasets/
├── raw/
│   └── cleaned.txt (cleaned corpus)
├── processed/
│   ├── tokenizer.json (trained tokenizer)
│   ├── vocab.json (vocabulary mappings)
│   ├── train.bin (90% of tokens, binary)
│   ├── val.bin (5% of tokens, binary)
│   └── test.bin (5% of tokens, binary)
└── stats.json (dataset statistics)
```

## Related Specifications

- [architecture.md](architecture.md) - Model architecture details
- [training.md](training.md) - Training loop using prepared data
