# backend/tracker/association.py
import hashlib
import numpy as np


def _stable_seed(*parts) -> int:
    """
    파이썬 내장 hash()는 프로세스마다 salt가 달라질 수 있어서,
    mock embedding은 안정적인 seed를 쓰는 게 좋다.
    """
    s = "|".join(map(str, parts)).encode("utf-8")
    digest = hashlib.sha256(s).digest()
    return int.from_bytes(digest[:4], "little")


def _l2norm(v: np.ndarray) -> np.ndarray:
    return v / (np.linalg.norm(v) + 1e-12)


def cosine(a: np.ndarray, b: np.ndarray) -> float:
    a = _l2norm(a)
    b = _l2norm(b)
    return float(np.dot(a, b))


def mock_embedding(true_id: int, dim: int = 128, noise: float = 0.02) -> np.ndarray:
    """
    같은 true_id면 항상 '비슷한' embedding이 나오도록:
    - true_id로 seed 고정 → base vector 고정
    - 프레임별로 작은 noise만 추가
    """
    rng = np.random.RandomState(_stable_seed(true_id))
    base = rng.randn(dim).astype(np.float32)
    base = _l2norm(base)

    emb = base + noise * np.random.randn(dim).astype(np.float32)
    emb = _l2norm(emb)
    return emb


class GlobalIDManager:
    """
    전역 ID 관리자 (최소 PoC 버전)
    - gallery: global_id -> 대표 embedding(EMA)
    - assign(): 새 embedding을 가장 가까운 global_id에 매칭, 없으면 새로 생성
    """
    def __init__(self, dim: int = 128, th: float = 0.75, ema: float = 0.9):
        self.dim = dim
        self.th = th
        self.ema = ema
        self.next_gid = 1
        self.gallery = {}  # gid -> np.ndarray(rep)

    def assign(self, emb: np.ndarray):
        best_gid, best_sim = None, -1.0

        for gid, rep in self.gallery.items():
            sim = cosine(emb, rep)
            if sim > best_sim:
                best_sim, best_gid = sim, gid

        # 새 사람
        if best_gid is None or best_sim < self.th:
            gid = self.next_gid
            self.next_gid += 1
            self.gallery[gid] = emb.copy()
            return gid, best_sim

        # 기존 사람: EMA 업데이트
        self.gallery[best_gid] = _l2norm(self.ema * self.gallery[best_gid] + (1.0 - self.ema) * emb)
        return best_gid, best_sim
