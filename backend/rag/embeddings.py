from chromadb.utils.embedding_functions import DefaultEmbeddingFunction

_ef = None

def get_embedding_function():
    global _ef
    if _ef is None:
        _ef = DefaultEmbeddingFunction()
    return _ef

def embed_texts(texts: list[str]) -> list:
    ef = get_embedding_function()
    return ef(texts)
