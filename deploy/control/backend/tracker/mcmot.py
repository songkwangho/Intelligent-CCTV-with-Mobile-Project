# backend/tracker/mcmot.py
import math

class SimpleTracker:
    """
    아주 단순한 NN(Nearest Neighbor) 트래커
    - 입력: [(x,y), ...]  (BEV 좌표)
    - 출력: [(track_id, x, y), ...]
    """
    def __init__(self, dist_th=40.0, max_age=15):
        self.dist_th = dist_th
        self.max_age = max_age
        self.next_id = 1
        self.tracks = {}   # track_id -> (x,y)
        self.age = {}      # track_id -> frames since seen

    def update(self, detections):
        # age 증가 및 만료
        for tid in list(self.age.keys()):
            self.age[tid] += 1
            if self.age[tid] > self.max_age:
                self.age.pop(tid, None)
                self.tracks.pop(tid, None)

        assigned = set()
        results = []

        for (x, y) in detections:
            best_id, best_d = None, 1e9

            for tid, (tx, ty) in self.tracks.items():
                if tid in assigned:
                    continue

                d = math.hypot(x - tx, y - ty)
                if d < best_d:
                    best_d, best_id = d, tid

            if best_id is None or best_d > self.dist_th:
                best_id = self.next_id
                self.next_id += 1

            self.tracks[best_id] = (x, y)
            self.age[best_id] = 0
            assigned.add(best_id)
            results.append((best_id, x, y))

        return results
