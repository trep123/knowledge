"""Sparse 向量编码：jieba 分词 + 词频计数，配合 Qdrant 服务端 IDF modifier。

词项索引采用 CRC32 稳定哈希（u32），无需维护全局词表。
"""
import re
import zlib

import jieba

STOPWORDS = set(
    "的 了 是 在 和 与 及 或 也 就 都 而 等 对 为 以 到 从 被 把 让 向 于 之 其 此 该 这 那 有 无 不 并 个 中 上 下 着 过 呢 吗 吧 啊 很 更 最 已 请 将 各 每 某 另 自 只 仅 便 能 会 要 可 应 该 需 如 若 因 所 按 依 据 由 至 当 再 又 多 少 大 小 我 你 他 她 它 我们 你们 他们".split()
)


def tokenize(text: str) -> list[str]:
    text = text.lower()
    tokens = []
    for t in jieba.cut(text):
        t = t.strip()
        if not t or t in STOPWORDS:
            continue
        if re.fullmatch(r"[\W_]+", t):
            continue
        tokens.append(t)
    return tokens


def encode_sparse(text: str) -> tuple[list[int], list[float]]:
    counts: dict[int, int] = {}
    for token in tokenize(text):
        idx = zlib.crc32(token.encode("utf-8")) & 0x7FFFFFFF
        counts[idx] = counts.get(idx, 0) + 1
    indices = sorted(counts)
    values = [float(counts[i]) for i in indices]
    return indices, values
