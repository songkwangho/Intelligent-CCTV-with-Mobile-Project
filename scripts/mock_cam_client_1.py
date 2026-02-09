import asyncio
import base64
import json
import math
import random
import time

import numpy as np
import websockets

SERVER = "ws://127.0.0.1:8001"
CAM_ID = 0


def make_embedding(person_id: int, dim: int = 128) -> np.ndarray:
    """Deterministic pseudo-embedding for testing (float32, unit norm)."""
    rng = random.Random(person_id)
    v = np.array([rng.uniform(-1.0, 1.0) for _ in range(dim)], dtype=np.float32)
    n = float(np.linalg.norm(v)) or 1.0
    return v / n


def pack_emb_b64_f16(emb_f32: np.ndarray) -> str:# float32 numpy -> float16 bytes -> base64 string
    """float32 numpy -> float16 bytes -> base64 string"""
    emb_f16 = emb_f32.astype(np.float16, copy=False)
    raw = emb_f16.tobytes(order="C")
    return base64.b64encode(raw).decode("ascii")


async def main():
    url = f"{SERVER}/ingest/{CAM_ID}"
    print("connect:", url)

    people = {
        0: [80.0, 80.0],
        1: [120.0, 120.0],
        2: [160.0, 160.0],
    }

    async with websockets.connect(url) as ws:
        while True:
            dets = []
            for pid, pos in people.items():
                pos[0] += random.uniform(-2.5, 2.5)
                pos[1] += random.uniform(-2.5, 2.5)

                true_id = CAM_ID * 100 + pid
                emb = make_embedding(true_id)  # float32
                #모바일 엣지로 넘어가면 emb는 AI로 만들면 됨

                dets.append(
                    {
                        "x": float(pos[0]),
                        "y": float(pos[1]),
                        "true_id": int(true_id),  # 디버그/호환용
                        # float16 base64 전송
                        "emb_b64": pack_emb_b64_f16(emb),
                        "emb_dtype": "float16",
                    }
                )

            msg = {"v": 1, "ts": time.time(), "detections": dets}
            await ws.send(json.dumps(msg))
            await asyncio.sleep(0.1)


if __name__ == "__main__":
    asyncio.run(main())
