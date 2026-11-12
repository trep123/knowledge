from app.rag.chunker import chunk_text

SENT = "这是一句测试文本，长度大约三十个字符左右的样子。"


def test_bad_overlap_does_not_duplicate():
    text = "\n".join([SENT] * 40)
    chunks = chunk_text(text, 100, 200)
    total = sum(len(c) for c in chunks)
    assert max(len(c) for c in chunks) <= 100
    assert total < len(text) * 2  # 原实现会膨胀约 8 倍


def test_normal_chunking_respects_size():
    text = "\n\n".join([SENT * 3] * 30)
    chunks = chunk_text(text, 200, 40)
    assert chunks and max(len(c) for c in chunks) <= 200


def test_oversized_paragraph_splits_on_sentence_boundaries():
    text = SENT * 60  # 一整段没有换行
    chunks = chunk_text(text, 200, 0)
    assert max(len(c) for c in chunks) <= 200
    assert all(c.endswith("。") for c in chunks[:-1])
