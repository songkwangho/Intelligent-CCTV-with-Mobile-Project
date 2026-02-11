"""backend/schemas.py

PoC 단계에서는 pydantic/PROTO 대신 TypedDict로 메시지 형태를 명시합니다.

용도
1) camera_init: 서버 -> 관제(viewer)
2) detected_data: 서버 -> 관제(viewer)
3) ingest: 엣지/카메라 -> 서버
"""

from __future__ import annotations

from typing import Dict, List, Literal, Optional, TypedDict


# ----------------------------
# camera registry -> viewer
# ----------------------------
class CameraCfg(TypedDict, total=False):
    name: str
    bev_x: float
    bev_y: float
    theta: float
    # Homography 3x3 (image -> BEV). In PoC it may be omitted.
    H: List[List[float]]


class CameraInitMsg(TypedDict):
    type: Literal["camera_init"]
    cameras: Dict[str, CameraCfg]


# ----------------------------
# ingest (edge -> server)
# ----------------------------
EmbeddingDtype = Literal["float16", "float32"]


class IngestDetection(TypedDict, total=False):
    """One person detection.

    좌표는 PoC에선 이미 BEV라고 가정하지만, 향후에는 bbox/foot_point 기반으로
    서버나 엣지에서 BEV로 변환하게 됩니다.
    """

    # legacy / PoC coords
    x: float
    y: float
    bev_x: float
    bev_y: float

    # optional debugging id used only for mocking
    true_id: int

    # optional confidence / bbox metadata (future)
    conf: float
    bbox: List[float]  # [x1,y1,x2,y2] on image
    foot: List[float]  # [u,v] on image (foot point)

    # ReID embedding (choose ONE of the two styles)
    embedding: List[float]  # easiest: raw float list
    emb_b64: str  # compact: base64 of float16/float32 bytes
    emb_dtype: EmbeddingDtype


class IngestMsg(TypedDict, total=False):
    """Edge/camera -> server message."""

    v: int  # schema version
    ts: float                 # edge send time (sec)
    frame_id: int
    seq: int                  # per-camera increasing sequence
    capture_ts_us: int        # capture timestamp in microseconds (key for video sync)
    detections: List[IngestDetection]

# ----------------------------
# server -> viewer
# ----------------------------
class BevPoint(TypedDict):
    bev_x: float
    bev_y: float


class BevTrackPoint(BevPoint, total=False):
    global_id: int
    sim: float
    ts: float


class DetectedDataMsg(TypedDict):
    type: Literal["detected_data"]
    data: Dict[str, Dict[str, BevTrackPoint]] # cam_id(str) -> track_id(str) -> payload

# camera status broadcast
class CameraStatus(TypedDict, total=False):
    online: bool
    last_seen_ts: float     # server receive time (sec)
    rx_fps: float
    last_seq: int
    seq_gap_count: int      # increments when a gap detected
    last_capture_ts_us: int # last capture timestamp seen


class CameraStatusMsg(TypedDict):
    type: Literal["camera_status"]
    status: Dict[str, CameraStatus]  # cam_id(str) -> status