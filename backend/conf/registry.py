# backend/conf/registry.py
from copy import deepcopy

# mock cam 정보 (PoC용: 나중에 갤럭시 카메라에서 들어올 것)
CAMERAS = {
    0: {"name": "Camera 1", "bev_x": 100, "bev_y": 200, "theta": -90,
        "H": [[1.2, 0.0, 50], [0.0, 1.2, 30], [0.0, 0.0, 1.0]]
    },
    1: {"name": "Camera 2", "bev_x": 400, "bev_y": 200, "theta": 180,
        "H": [[1.2, 0.0, 100], [0.0, 1.2, 60], [0.0, 0.0, 1.0]]
    },
}

# ✅ cam_id별 ingest 토큰 (PoC용: 나중에 안전한 키로 교체)
CAM_TOKENS = {
    0: "dev-token-cam0",
    1: "dev-token-cam1",
    2: "dev-token-cam2",
}

def get_cameras_for_runtime():
    """
    내부 계산용.
    - key: int (cam_id)
    - value: dict (camera config)
    """
    return deepcopy(CAMERAS)

def get_cameras_for_message():
    """
    프론트로 보낼 때는 key가 문자열이어야 JS에서 안정적으로 순회됨.
    - key: str
    """
    cams = deepcopy(CAMERAS)
    return {str(cid): cfg for cid, cfg in cams.items()}

def get_cam_token(cam_id: int) -> str | None:
    return CAM_TOKENS.get(cam_id)