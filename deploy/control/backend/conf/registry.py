# backend/conf/registry.py

"""Camera registry (PoC).

이 버전은 **"활성(connected) 카메라만 UI에 노출"** 하는 것을 목표로 합니다.

데이터 구조:
- CAMERA_DEFAULTS: 설치/캘리브레이션 기본값. UI에 직접 뿌리지 않음.
- CAMERAS_RUNTIME: 런타임 활성 카메라만 저장. UI에는 이 목록만 전송.

카메라가 접속하면:
- ingest(/ingest/{cam_id})가 시작되거나 
  /ui로 cam_meta가 1회 도착하면 cam 정보가
  CAMERAS_RUNTIME에 등록되고 map.html에 표시됩니다.
"""

from __future__ import annotations

from copy import deepcopy
import time
from typing import Dict, Any, Optional, Tuple

# -----------------------------------------------------------------------------
# Static defaults (optional): camera install/calibration defaults
# - UI에는 직접 뿌리지 않음
# - CAMERAS_RUNTIME에 처음 등록될 때 base로 사용
# -----------------------------------------------------------------------------
CAMERA_DEFAULTS: Dict[int, Dict[str, Any]] = {
    0: {
        "name": "Camera 0",
        "bev_x": 100,
        "bev_y": 200,
        "theta": -90,
        "H": [[1.2, 0.0, 50], [0.0, 1.2, 30], [0.0, 0.0, 1.0]],
    },
    1: {
        "name": "Camera 1",
        "bev_x": 400,
        "bev_y": 200,
        "theta": 180,
        "H": [[1.2, 0.0, 100], [0.0, 1.2, 60], [0.0, 0.0, 1.0]],
    },
}


# -----------------------------------------------------------------------------
# Runtime active cameras
# - UI(map/video)에 전달되는 카메라 목록은 이것만 사용
# -----------------------------------------------------------------------------
CAMERAS_RUNTIME: Dict[int, Dict[str, Any]] = {}


# ✅ cam_id별 ingest 토큰 (PoC용: 나중에 안전한 키로 교체)
CAM_TOKENS: Dict[int, str] = {
    0: "dev-token-cam0",
    1: "dev-token-cam1",
    2: "dev-token-cam2",
}


def get_cam_token(cam_id: int) -> Optional[str]:
    """Return PoC token for the given cam_id.

    Args:
        cam_id: Camera identifier.

    Returns:
        Token string if registered, else None.
    """
    return CAM_TOKENS.get(cam_id)


def get_cameras_for_runtime() -> Dict[int, Dict[str, Any]]:
    """Return a deep-copied snapshot of currently active(runtime) cameras.

    Notes:
        Internal calculations may prefer integer keys.
    """
    return deepcopy(CAMERAS_RUNTIME)


def get_cameras_for_message() -> Dict[str, Dict[str, Any]]:
    """Return cameras payload for frontend.

    Returns:
        Dict where keys are **strings** (JS-friendly), values are camera configs.

    Important:
        Only runtime active cameras are returned.
    """
    cams = get_cameras_for_runtime()
    return {str(camid): cfg for camid, cfg in cams.items()}


def _default_bev_xy(cam_id: int) -> Tuple[float, float]:
    """Generate a deterministic *temporary* BEV position for cameras without calibration.

    This prevents all newly added cameras from stacking at (0,0).
    """
    x = 80.0 + (cam_id % 6) * 110.0
    y = 80.0 + ((cam_id // 6) % 6) * 110.0
    return x, y


def upsert_camera(cam_id_str: str, meta: Dict[str, Any]) -> bool:
    """Create or update a runtime camera entry.

    Args:
        cam_id_str: Camera id as string (e.g. "0").
        meta: Arbitrary camera metadata. Common keys:
            - name: human readable name
            - bev_x, bev_y: BEV map position
            - theta: orientation(deg)
            - H: homography(3x3)
            - any extra fields are preserved

    Returns:
        True if this was a **new** runtime camera; False if updated existing.
    """
    try:
        cid = int(cam_id_str)
    except Exception:
        return False

    is_new = cid not in CAMERAS_RUNTIME

    # Start from defaults if present
    cur = deepcopy(CAMERA_DEFAULTS.get(cid, {})) if is_new else CAMERAS_RUNTIME[cid]

    # Ensure minimal fields
    if "bev_x" not in cur or "bev_y" not in cur:
        dx, dy = _default_bev_xy(cid)
        cur.setdefault("bev_x", dx)
        cur.setdefault("bev_y", dy)

    cur.setdefault("name", f"Camera {cid}")

    # Merge incoming metadata (only provided keys)
    for k, v in (meta or {}).items():
        if k == "cam_id":
            continue
        cur[k] = v

    # last_seen is used for optional pruning
    cur["last_seen_ts"] = time.time()

    CAMERAS_RUNTIME[cid] = cur
    return is_new


def touch_camera(cam_id: int) -> bool:
    """Mark a camera as active (seen recently).

    This is called on each ingest message.
    If the camera wasn't registered in runtime yet, it will be created.

    Args:
        cam_id: Camera identifier.

    Returns:
        True if the camera was newly added to runtime.
    """
    if cam_id in CAMERAS_RUNTIME:
        CAMERAS_RUNTIME[cam_id]["last_seen_ts"] = time.time()
        return False
    return upsert_camera(str(cam_id), {"cam_id": str(cam_id)})


def remove_camera_runtime(cam_id: int) -> bool:
    """Remove a camera from runtime list.

    Useful when ingest websocket disconnects.

    Returns:
        True if removed; False if it didn't exist.
    """
    if cam_id in CAMERAS_RUNTIME:
        del CAMERAS_RUNTIME[cam_id]
        return True
    return False


def prune_offline(ttl_sec: float = 10.0) -> list[int]:
    """Remove cameras that haven't been seen for ttl_sec.

    This is optional. If you want cameras to remain visible after disconnect,
    you can avoid calling this.

    Returns:
        List of cam_ids removed.
    """
    now = time.time()
    removed: list[int] = []
    for cid, cfg in list(CAMERAS_RUNTIME.items()):
        last_seen = float(cfg.get("last_seen_ts", 0.0))
        if now - last_seen > ttl_sec:
            removed.append(cid)
            del CAMERAS_RUNTIME[cid]
    return removed
