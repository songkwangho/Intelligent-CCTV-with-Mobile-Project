# backend/bev/world_map.py
from dataclasses import dataclass

@dataclass
class WorldMap:
    """
    BEV 지도(픽셀 좌표계) 메타정보를 담는 용도.
    지금은 프론트에서 clamp를 하니 최소만 둠.
    """
    width: int = 500
    height: int = 500

    def clamp(self, x: float, y: float):
        cx = max(0, min(self.width, x))
        cy = max(0, min(self.height, y))
        return cx, cy
