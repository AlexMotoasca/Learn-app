import os, json, faiss, numpy as np
from sentence_transformers import SentenceTransformer

EMB_MODEL_NAME = "paraphrase-multilingual-MiniLM-L12-v2"
MODEL = SentenceTransformer(EMB_MODEL_NAME)

MODULES_DIR = "Lessons/biologie"
INDEX_FILE = "storage/index.faiss"
META_FILE = "storage/meta.json"
os.makedirs("storage", exist_ok=True)

def split_chunks(text, max_len=600, overlap=80):
    chunks = []
    i = 0
    while i < len(text):
        chunk = text[i:i+max_len]
        chunks.append(chunk.strip())
        i += max_len - overlap
    return [c for c in chunks if c]

texts, metas = [], []

for filename in sorted(os.listdir(MODULES_DIR)):
    if filename.startswith("modul") and filename.endswith(".txt"):
        path = os.path.join(MODULES_DIR, filename)
        module_number = int(filename.replace("modul", "").replace(".txt", ""))

        with open(path, "r", encoding="utf-8") as f:
            content = f.read().strip()

        chunks = split_chunks(content)
        for idx, chunk in enumerate(chunks):
            texts.append(chunk)
            metas.append({"module": module_number, "chunk_id": idx, "text": chunk})

emb = MODEL.encode(texts, convert_to_numpy=True, batch_size=64, normalize_embeddings=True)

index = faiss.IndexFlatIP(emb.shape[1])  # cosine via dot on normalized vectors
index.add(emb)

faiss.write_index(index, INDEX_FILE)
with open(META_FILE, "w", encoding="utf-8") as f:
    json.dump(metas, f, ensure_ascii=False, indent=2)

print("✅ Indexing complete:", INDEX_FILE, META_FILE)
