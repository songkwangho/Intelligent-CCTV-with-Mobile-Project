# backend/websocket.py
import asyncio
import base64
import time
import logging

from collections import deque
from typing import Dict, Any, List, Optional, Set

import numpy as np
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from backend.conf.registry import get_cameras_for_message, get_cam_token # token auth 쓰는 경우
from backend.tracker.mcmot import SimpleTracker
from backend.tracker.association import GlobalIDManager, mock_embedding

ws_router = APIRouter()

logger = logging.getLogger("ingest")
logger.setLevel(logging.INFO)

# ----------------------------
# Global server states
# ----------------------------
viewers: Set[WebSocket] = set()                   # /ws로 붙는 프론트들
state_lock = asyncio.Lock()
latest_by_cam: Dict[str, Dict[str, Any]] = {}     # cam_id(str) -> track_id(str) -> payload

# tracker/association
trackers: Dict[int, SimpleTracker] = {}           # cam_id(int) -> SimpleTracker
gid_manager = GlobalIDManager(dim=128, th=0.75, ema=0.9)

# cam stats
# cam_id(str) -> stats dict
cam_stats: Dict[str, Dict[str, Any]] = {}
FPS_WINDOW_SEC = 2.0

def _ensure_tracker(cam_id: int) -> SimpleTracker:
    if cam_id not in trackers:
        trackers[cam_id] = SimpleTracker(dist_th=35.0, max_age=20)
    return trackers[cam_id]

def _parse_embedding(
    det: Dict[str, Any],
    expected_dim: int,
    *,
    cam_id: int,
    frame_id: Optional[int],
    det_index: int
) -> Optional[np.ndarray]:
    """Parse embedding from a detection.

    Supports two formats:
    1) embedding: List[float]
    2) emb_b64: base64 encoded raw bytes, with emb_dtype: float16|float32

    Returns float32 numpy array (expected_dim,), or None.
    Logs clear reason on failures.
    """
    try:
        if "embedding" in det and det["embedding"] is not None:
            arr = np.asarray(det["embedding"], dtype=np.float32)

        elif "emb_b64" in det and det.get("emb_b64"):
            b64 = det["emb_b64"]
            try:
                raw = base64.b64decode(b64)
            except Exception as e:
                logger.warning("emb_b64 decode failed cam=%s frame=%s det=%s err=%s",
                    cam_id, frame_id, det_index, repr(e)
                )
                return None

            dtype = det.get("emb_dtype", "float16")
            if dtype not in ("float16", "float32"):
                logger.warning(
                    "emb_dtype invalid cam=%s frame=%s det=%s dtype=%s (expected float16|float32)",
                    cam_id, frame_id, det_index, dtype
                )
                return None

            np_dtype = np.float16 if dtype == "float16" else np.float32
            arr = np.frombuffer(raw, dtype=np_dtype).astype(np.float32, copy=False)

        else:
            # embedding not provided
            return None

        if arr.ndim != 1:
            logger.warning(
                "embedding shape invalid cam=%s frame=%s det=%s ndim=%s",
                cam_id, frame_id, det_index, arr.ndim
            )
            return None

        if arr.size != expected_dim:
            logger.warning(
                "embedding dim mismatch cam=%s frame=%s det=%s dim=%s expected=%s",
                cam_id, frame_id, det_index, arr.size, expected_dim
            )
            return None

        # Optional: normalize on server too (safety net)
        # n = np.linalg.norm(arr) + 1e-12
        # arr = arr / n

        return arr

    except Exception as e:
        logger.warning(
            "embedding parse error cam=%s frame=%s det=%s err=%s",
            cam_id, frame_id, det_index, repr(e)
        )
        return None


def _update_cam_stats(cam_id: str, *, seq: Optional[int], capture_ts_us: Optional[int]) -> None:
    now = time.time()
    st = cam_stats.get(cam_id)
    if st is None:
        st = {
            "times": deque(),         # receive times
            "last_seen_ts": 0.0,
            "last_seq": None,
            "seq_gap_count": 0,
            "last_capture_ts_us": None,
        }
        cam_stats[cam_id] = st

    st["last_seen_ts"] = now
    if capture_ts_us is not None:
        st["last_capture_ts_us"] = int(capture_ts_us)

    # fps window
    times: deque = st["times"]
    times.append(now)
    cutoff = now - FPS_WINDOW_SEC
    while times and times[0] < cutoff:
        times.popleft()

    # seq gap detection
    if seq is not None:
        prev = st["last_seq"]
        if prev is not None and int(seq) > int(prev) + 1:
            st["seq_gap_count"] += 1
        st["last_seq"] = int(seq)


def _build_camera_status_payload() -> Dict[str, Any]:
    now = time.time()
    out: Dict[str, Any] = {}
    for cam_id, st in cam_stats.items():
        times: deque = st.get("times", deque())
        rx_fps = float(len(times) / FPS_WINDOW_SEC) if FPS_WINDOW_SEC > 0 else 0.0
        last_seen = float(st.get("last_seen_ts", 0.0))
        online = (now - last_seen) <= 3.0  # 3초 내 수신이면 online
        out[cam_id] = {
            "online": online,
            "last_seen_ts": last_seen,
            "rx_fps": rx_fps,
            "last_seq": st.get("last_seq") if st.get("last_seq") is not None else -1,
            "seq_gap_count": int(st.get("seq_gap_count", 0)),
            "last_capture_ts_us": st.get("last_capture_ts_us") if st.get("last_capture_ts_us") is not None else -1,
        }
    return out

async def broadcast_camera_status():
    payload = {"type": "camera_status", "status": _build_camera_status_payload()}
    dead = []
    for ws in list(viewers):
        try:
            await ws.send_json(payload)
        except Exception:
            dead.append(ws)
    for ws in dead:
        viewers.discard(ws)

async def broadcast_detected_data():
    """
    최신 상태(latest_by_cam)를 모든 viewer에게 브로드캐스트
    """
    async with state_lock:
        payload = {"type": "detected_data", "data": latest_by_cam}

    dead = []
    for ws in list(viewers):
        try:
            await ws.send_json(payload)
        except Exception:
            dead.append(ws)

    for ws in dead:
        viewers.discard(ws)


# ----------------------------
# Viewer WebSocket (frontend) - 프론트가 붙는 곳(브로드캐스트 수신)
# ----------------------------
@ws_router.websocket("/ws")
async def viewer_ws(ws: WebSocket):
    await ws.accept()
    viewers.add(ws)

    # 1) camera_init 먼저 전송 (프론트가 카메라 위치 그리도록)
    cams_msg = get_cameras_for_message()
    await ws.send_json({"type": "camera_init", "cameras": cams_msg})

    # 2) 접속 직후 현재 상태 1회 전송(이미 ingest가 돌고 있을 수 있으니)
    await broadcast_detected_data()
    await broadcast_camera_status()

    try:
        # viewer는 보통 서버로 보낼 게 없으므로 그냥 유지
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        viewers.discard(ws)
        try:
            await ws.close()
        except Exception:
            pass


# ----------------------------
# Camera ingest WebSocket - 카메라(클라이언트)가 보내는 곳(수집)
# ----------------------------
@ws_router.websocket("/ingest/{cam_id}")
async def ingest_ws(ws: WebSocket, cam_id: int):
    """
    카메라/엣지에서 detection(+embedding)을 서버로 보내는 채널

    기대 포맷(최소):
    {
      "ts": 123456.7,
      "detections": [
        {"x": 120.1, "y": 33.2, "true_id": 0},
        {"x": 130.2, "y": 36.0, "true_id": 1}
      ]
    }

    - x,y는 이미 BEV 좌표라고 가정(지금은 mock 단계)
    - true_id는 mock embedding용(실제로는 embedding을 넣으면 됨)
    - track_id가 없으면 server가 SimpleTracker로 local track_id를 부여
    """
    await ws.accept()

    # (선택) 토큰 인증을 이미 쓰고 있다면 유지
    expected = get_cam_token(cam_id)
    provided = ws.headers.get("x-edge-token")
    if expected is None:
        # 등록되지 않은 카메라 ID
        await ws.close(code=1008, reason="cam not registered")  # policy violation
        return

    if provided != expected:
        await ws.close(code=1008, reason="unauthorized")
        return

    tracker = _ensure_tracker(cam_id)
    cam_key = str(cam_id)

    try:
        while True:
            msg = await ws.receive_json()
            dets = msg.get("detections", [])
            frame_id = msg.get("frame_id")

            # stats update (seq/capture_ts_us)
            seq = msg.get("seq")
            capture_ts_us = msg.get("capture_ts_us")
            _update_cam_stats(cam_key, seq=seq, capture_ts_us=capture_ts_us)

            # (1) detections -> (x,y, embedding) 리스트로 변환
            xy = []
            embeddings: List[Optional[np.ndarray]] = []
            true_ids = []
            
            for idx, d in enumerate(dets):
                x = d.get("bev_x", d.get("x"))
                y = d.get("bev_y", d.get("y"))
                if x is None or y is None:
                    continue
                xy.append((float(x), float(y)))
                embeddings.append(
                    _parse_embedding(d,expected_dim=gid_manager.dim,cam_id=cam_id,frame_id=frame_id,det_index=idx))
                true_ids.append(int(d.get("true_id", 0)))

            # (2) local tracking (cam 내부 track_id 안정화)
            tracks = tracker.update(xy)

            # (3) global id 부여 + 최신 상태 업데이트
            cam_out: Dict[str, Any] = {}
            for tidx, (track_id, x, y) in enumerate(tracks):
                # 1) embedding이 오면 그것을 우선 사용
                emb = embeddings[tidx] if tidx < len(embeddings) else None

                # 2) embedding이 없으면 (호환/테스트용) true_id 기반 mock 사용
                if emb is None:
                    pid = true_ids[tidx] if tidx < len(true_ids) else 0
                    emb = mock_embedding(pid)

                gid, sim = gid_manager.assign(emb)

                cam_out[str(track_id)] = {
                    "bev_x": float(x),
                    "bev_y": float(y),
                    "global_id": int(gid),
                    "sim": float(sim),
                    "ts": float(msg.get("ts", time.time())),
                }

            async with state_lock:
                latest_by_cam[cam_key] = cam_out

            # (4) viewer들에게 브로드캐스트
            await broadcast_detected_data()
            await broadcast_camera_status()

    except WebSocketDisconnect:
        pass
    finally:
        try:
            await ws.close()
        except Exception:
            pass
    # 접속 종료 시 해당 카메라 데이터 삭제
