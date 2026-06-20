"""Embed every FAQ file into ChromaDB. Idempotent — safe to re-run.

Each file in knowledge_base/faq/*.txt is one topic/question. We re-ingest a file
by first deleting its previous chunks (keyed by `source`), so edits and deletions
don't leave stale vectors behind.

Run from chatbot-service/:  python knowledge_base/ingest.py
"""

import hashlib
import logging
import sys
from pathlib import Path

# Allow running as a plain script from chatbot-service/.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from langchain_text_splitters import RecursiveCharacterTextSplitter  # noqa: E402

from app.core.config import settings  # noqa: E402
from app.rag.store import get_collection  # noqa: E402

logging.basicConfig(level=settings.log_level)
logger = logging.getLogger("ingest")

# chunk_size/overlap in config are token-oriented; approximate ~4 chars/token.
CHARS_PER_TOKEN = 4


def _file_id(path: Path, idx: int) -> str:
    h = hashlib.sha1(str(path.name).encode()).hexdigest()[:10]
    return f"{h}-{idx}"


def main() -> None:
    kb_dir = Path(settings.knowledge_base_dir)
    if not kb_dir.exists():
        logger.error("Knowledge base dir not found: %s", kb_dir)
        return

    files = sorted(kb_dir.glob("*.txt"))
    if not files:
        logger.warning("No .txt files in %s", kb_dir)
        return

    collection = get_collection()
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=settings.rag_chunk_size * CHARS_PER_TOKEN,
        chunk_overlap=settings.rag_chunk_overlap * CHARS_PER_TOKEN,
    )

    total_chunks = 0
    for path in files:
        text = path.read_text(encoding="utf-8").strip()
        if not text:
            continue
        # Drop any previous chunks for this file (idempotent re-ingest).
        collection.delete(where={"source": path.name})

        chunks = splitter.split_text(text)
        ids = [_file_id(path, i) for i in range(len(chunks))]
        metadatas = [{"source": path.name, "chunk": i} for i in range(len(chunks))]
        collection.upsert(ids=ids, documents=chunks, metadatas=metadatas)
        total_chunks += len(chunks)
        logger.info("Ingested %s -> %d chunk(s)", path.name, len(chunks))

    logger.info(
        "Done. %d file(s), %d chunk(s) in collection '%s' at %s",
        len(files), total_chunks, settings.chroma_collection, settings.chroma_persist_dir,
    )


if __name__ == "__main__":
    main()
