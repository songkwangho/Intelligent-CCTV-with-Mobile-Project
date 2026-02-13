# backend/websocket.py
import asyncio
import base64
import time
import logging

from collections import deque
from typing import Dict, Any, List, Optional, Set

import numpy as np
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from backend.conf import registry as cam_registry
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
cam_stats: Dict[str, Dict[str, Any]] = {}

# UI clients (map/video 같은 UI 브라우저들이 붙는 채널)
ui_clients: Set[WebSocket] = set()
# focus gid state (UI 동기화용)
focused_gid: Optional[int] = None

FPS_WINDOW_SEC = 2.0

async def prune_runtime_cameras(ttl_sec: float = 5.0) -> List[int]:
    """Prune offline cameras from the runtime registry.

    목적
    - /ui로 cam_meta는 왔는데 앱이 강제종료되어 disconnect 처리가 안 되면
      runtime 레지스트리에 카메라가 남아 map에 계속 보일 수 있음(=유령 카메라).
    - TTL 기반 정리를 백그라운드에서 돌려 안전장치로 사용.

    동작
    - registry.CAMERAS_RUNTIME 에서 last_seen_ts 기준 ttl_sec 초과 카메라 제거
    - 제거된 카메라의 최신프레임/통계(state)도 함께 정리
    - /ws 시청자(map.html 등)에게 camera_update 브로드캐스트
    """
    removed = cam_registry.prune_offline(ttl_sec=ttl_sec)
    if not removed:
        return []

    # per-cam 최신/통계 정리
    async with state_lock:
        for cid in removed:
            latest_by_cam.pop(str(cid), None)

    for cid in removed:
        cam_stats.pop(str(cid), None)

    await broadcast_camera_update()
    return removed

def _ensure_tracker(cam_id: int) -> SimpleTracker:
    """Get or create per-camera local tracker.

    The local tracker stabilizes per-camera `track_id` so that Global ReID
    doesn't have to deal with jittery IDs.
    """
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

    Returns:
        float32 numpy array (expected_dim,), or None.

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

        return arr

    except Exception as e:
        logger.warning(
            "embedding parse error cam=%s frame=%s det=%s err=%s",
            cam_id, frame_id, det_index, repr(e)
        )
        return None

def _update_cam_stats(cam_id: str, *, seq: Optional[int], capture_ts_us: Optional[int]) -> None:
    """Update per-camera ingest stats used for online/fps display/debug."""
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
    """Build a status payload for debugging (online/fps/seq gaps)."""
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
    """Broadcast camera_status to all `/ws` viewers."""
    payload = {"type": "camera_status", "status": _build_camera_status_payload()}

    dead = []
    for ws in list(viewers):
        try:
            await ws.send_json(payload)
        except Exception:
            dead.append(ws)
    for ws in dead:
        viewers.discard(ws)


async def broadcast_camera_update():
    """Broadcast current **runtime(active)** camera list to all viewers(/ws).

    Important:
        `cam_registry.get_cameras_for_message()` should return only active cameras.
        That is what makes "emulator 1대면 1개만 보이기"가 가능합니다.
    """
    cams_msg = cam_registry.get_cameras_for_message()
    payload = {"type": "camera_update", "cameras": cams_msg}

    dead = []
    for ws in list(viewers):
        try:
            await ws.send_json(payload)
        except Exception:
            dead.append(ws)
    for ws in dead:
        viewers.discard(ws)


async def broadcast_detected_data():
    """Broadcast latest_by_cam snapshot to all `/ws` viewers."""
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

    # camera_init: "현재 활성 카메라"만 전송
    cams_msg = cam_registry.get_cameras_for_message()
    await ws.send_json({"type": "camera_init", "cameras": cams_msg})

    await broadcast_detected_data()
    await broadcast_camera_status()

    try:
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
# UI/control WebSocket (/ui)
# ----------------------------
@ws_router.websocket("/ui")
async def ui_ws(ws: WebSocket):
    """UI/control WebSocket.

    Used for:
    - focus_gid sync between map.html and video.html
    - cam_meta from edge devices (emulator/phones) to dynamically register cameras

    Message examples:
      {"type":"focus_gid", "data": {"gid": 12}}
      {"type":"cam_meta", "data": {"cam_id":"0","name":"EdgeCam-0","bev_x":120,"bev_y":80,"theta":0}}
    """
    await ws.accept()
    ui_clients.add(ws)
    try:
        await ws.send_json({"type": "ui_hello", "data": {"ok": True}})
        # 새로 접속한 UI에게 현재 focus 상태를 즉시 알려줌
        await ws.send_json({"type": "focus_gid", "data": {"gid": focused_gid}})
        while True:
            msg = await ws.receive_json()
            # logger.info("ui msg=%s", msg)#ui 연결 수신 확인용 로거, 확인후 주석처리 

            mtype = msg.get("type")
            data = msg.get("data", {})

            if mtype == "focus_gid":
                gid = data.get("gid")
                if gid is None or gid == "" or gid == "null":
                    focused_gid = None
                else:
                    try:
                        focused_gid = int(gid)
                    except Exception:
                        focused_gid = None

                # ✅ 서버가 정규화한 focus 메시지로 통일해서 broadcast
                msg = {"type": "focus_gid", "data": {"gid": focused_gid}}
                mtype = "focus_gid"

            # cam_meta 수신 → registry(runtime) 업데이트 → /ws에 camera_update 브로드캐스트
            if mtype == "cam_meta":
                cam_id = data.get("cam_id")
                if cam_id is not None:
                    cam_registry.upsert_camera(str(cam_id), data)
                    await broadcast_camera_update()

            # UI 이벤트는 그대로 브로드캐스트 (map↔video 동기화)
            dead = []
            for c in list(ui_clients):
                try:
                    await c.send_json(msg)
                except Exception:
                    dead.append(c)
            for c in dead:
                ui_clients.discard(c)
    
    except WebSocketDisconnect:
        pass
    finally:
        ui_clients.discard(ws)
        try:
            await ws.close()
        except Exception:
            pass


# ----------------------------
# Camera ingest WebSocket - detection(+embedding) 수집
# ----------------------------
@ws_router.websocket("/ingest/{cam_id}")
async def ingest_ws(ws: WebSocket, cam_id: int):
    """Ingest WebSocket from edge devices.

    Expected message (v1):
      {
        "v": 1,
        "ts": ...,
        "frame_id": ...,
        "seq": ...,
        "capture_ts_us": ...,
        "detections": [
          {"bev_x":..., "bev_y":..., "emb_b64":..., "emb_dtype":"float16"},
          ...
        ]
      }

    Notes:
      - video stream is handled separately via MediaMTX (RTSP/WebRTC).
      - registry는 runtime(active)만 UI에 노출하도록 설계됨.
    """
    await ws.accept()

    # 토큰 인증 (ingest만)
    expected = cam_registry.get_cam_token(cam_id)
    provided = ws.headers.get("x-edge-token")
    if expected is None:
        await ws.close(code=1008, reason="cam not registered")
        return
    if provided != expected:
        await ws.close(code=1008, reason="unauthorized")
        return

    tracker = _ensure_tracker(cam_id)
    cam_key = str(cam_id)

    # ---------------------------------------------------------------------
    # 활성(connected) 카메라만 UI에 노출
    # - ingest가 시작되면 touch_camera()로 runtime에 등록
    # - 새로 등록된 경우에만 camera_update 브로드캐스트
    # ---------------------------------------------------------------------
    is_new_cam = cam_registry.touch_camera(cam_id)
    if is_new_cam:
        await broadcast_camera_update()

    try:
        while True:
            msg = await ws.receive_json()
            dets = msg.get("detections", [])
            frame_id = msg.get("frame_id")

            # ingest 메시지를 받는 동안 이 카메라를 "활성" 상태로 유지
            cam_registry.touch_camera(cam_id)

            # stats update
            seq = msg.get("seq")
            capture_ts_us = msg.get("capture_ts_us")
            _update_cam_stats(cam_key, seq=seq, capture_ts_us=capture_ts_us)

            # (1) detections -> xy / embeddings
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
                    _parse_embedding(
                        d,
                        expected_dim=gid_manager.dim,
                        cam_id=cam_id,
                        frame_id=frame_id,
                        det_index=idx
                    )
                )
                true_ids.append(int(d.get("true_id", 0)))

            # (2) local tracking
            tracks = tracker.update(xy)

            # (3) global id
            cam_out: Dict[str, Any] = {}
            for tidx, (track_id, x, y) in enumerate(tracks):
                emb = embeddings[tidx] if tidx < len(embeddings) else None
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

            await broadcast_detected_data()
            await broadcast_camera_status()

    except WebSocketDisconnect:
        pass
    finally:
        # 접속 종료 시 해당 카메라를 runtime에서 제거(UX: "켜진 카메라만 보이기")
        removed = cam_registry.remove_camera_runtime(cam_id)
        if removed:
            await broadcast_camera_update()

        # 최신 상태에서도 제거
        async with state_lock:
            if cam_key in latest_by_cam:
                del latest_by_cam[cam_key]

        # (선택) cam_stats도 정리
        if cam_key in cam_stats:
            del cam_stats[cam_key]

        try:
            await ws.close()
        except Exception:
            pass
