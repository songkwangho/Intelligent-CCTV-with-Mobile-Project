// frontend/canvas.js
(function (global) {
  console.log("[canvas.js] loaded"); // ✅ 로드 확인용

  class BEVRenderer {
    constructor(bgCanvas, trailCanvas, dotCanvas, opts) {
      this.bgCanvas = bgCanvas;
      this.trailCanvas = trailCanvas;
      this.dotCanvas = dotCanvas;

      this.bgCtx = bgCanvas.getContext("2d");
      this.trailCtx = trailCanvas.getContext("2d");
      this.dotCtx = dotCanvas.getContext("2d");

      this.HISTORY_LEN = opts.historyLen ?? 50;
      this.TTL_FRAMES = opts.ttlFrames ?? 15;
      this.JUMP_TH = opts.jumpThPx ?? 80;      // 점프 임계값(px). 상황 보고 조절
      this.GAP_FRAMES = opts.gapFrames ?? 2;   // 몇 프레임 이상 끊기면 궤적 끊기
      this.BREAK_ON_CAM_CHANGE = (opts.breakOnCamChange ?? true);

      this.frameIdx = 0;

      this.colorMap = new Map();   // key -> color
      this.history = new Map();    // key -> [{x,y}, ...]
      this.lastSeen = new Map();   // key -> frameIdx
    }

    getColor(key) {
      if (!this.colorMap.has(key)) {
        this.colorMap.set(key, `hsl(${Math.random() * 360}, 80%, 50%)`);
      }
      return this.colorMap.get(key);
    }

    camXY(cam) {
      if (Number.isFinite(cam.x) && Number.isFinite(cam.y)) return [cam.x, cam.y];
      if (Array.isArray(cam.pos) && cam.pos.length >= 2) return [cam.pos[0], cam.pos[1]];
      if (Number.isFinite(cam.bev_x) && Number.isFinite(cam.bev_y)) return [cam.bev_x, cam.bev_y];
      return [null, null];
    }

    drawCamera(camId, cam) {
      const [x, y] = this.camXY(cam);
      if (!Number.isFinite(x) || !Number.isFinite(y)) return;

      const name = cam.name ?? `C${camId}`;
      const thetaDeg = cam.theta ?? 0;
      const rad = (thetaDeg * Math.PI) / 180.0;

      this.bgCtx.fillStyle = "gray";
      this.bgCtx.beginPath();
      this.bgCtx.arc(x, y, 8, 0, 2 * Math.PI);
      this.bgCtx.fill();

      this.bgCtx.strokeStyle = "gray";
      this.bgCtx.lineWidth = 2;
      this.bgCtx.beginPath();
      this.bgCtx.moveTo(x, y);
      this.bgCtx.lineTo(x + 20 * Math.cos(rad), y + 20 * Math.sin(rad));
      this.bgCtx.stroke();

      this.bgCtx.fillStyle = "gray";
      this.bgCtx.font = "12px sans-serif";
      this.bgCtx.fillText(name, x + 10, y - 10);
    }

    renderCameraInit(cameras) {
      this.bgCtx.clearRect(0, 0, this.bgCanvas.width, this.bgCanvas.height);
      for (const camId in cameras) {
        this.drawCamera(camId, cameras[camId]);
      }
    }

    redrawTrails() {
      this.trailCtx.clearRect(0, 0, this.trailCanvas.width, this.trailCanvas.height);

      for (const [key, pts] of this.history.entries()) {
        if (pts.length < 2) continue;

        const col = this.getColor(key);
        this.trailCtx.strokeStyle = col;
        this.trailCtx.lineWidth = 2;

        this.trailCtx.beginPath();
        this.trailCtx.moveTo(pts[0].x, pts[0].y);

        for (let i = 1; i < pts.length; i++) {
            const prev = pts[i - 1];
            const cur = pts[i];

            const dist = Math.hypot(cur.x - prev.x, cur.y - prev.y);
            const camSwitch = this.BREAK_ON_CAM_CHANGE && (prev.camId !== cur.camId);
            const gap = (cur.frame - prev.frame) > this.GAP_FRAMES;

            // 여기서 끊는다 (moveTo)
            if (camSwitch || gap || dist > this.JUMP_TH) {
            this.trailCtx.moveTo(cur.x, cur.y);
            } else {
            this.trailCtx.lineTo(cur.x, cur.y);
            }
        }

        this.trailCtx.stroke();
        }
    }

    drawDot(key, x, y, label) {
      const col = this.getColor(key);

      this.dotCtx.fillStyle = col;
      this.dotCtx.beginPath();
      this.dotCtx.arc(x, y, 6, 0, Math.PI * 2);
      this.dotCtx.fill();

      this.dotCtx.fillStyle = "black";
      this.dotCtx.font = "12px sans-serif";
      this.dotCtx.fillText(label, x + 8, y - 8);
    }

    renderDetectedData(data) {
      this.frameIdx += 1;

      // ✅ FIX: drawn 반드시 선언
      let drawn = 0;

      // dot은 현재 프레임만
      this.dotCtx.clearRect(0, 0, this.dotCanvas.width, this.dotCanvas.height);

      for (const camId in data) {
        const tracks = data[camId] || {};
        for (const trackId in tracks) {
          const p = tracks[trackId] || {};

          // 숫자 캐스팅(문자열로 와도 처리)
          const x = Number(p.bev_x ?? p.x);
          const y = Number(p.bev_y ?? p.y);
          if (!Number.isFinite(x) || !Number.isFinite(y)) continue;

          const cx = Math.max(0, Math.min(this.dotCanvas.width, x));
          const cy = Math.max(0, Math.min(this.dotCanvas.height, y));

          // ✅ global_id가 있으면 global로 key 고정
          const gid = p.global_id;
          const key = (gid !== undefined && gid !== null) ? `G${gid}` : `${camId}:${trackId}`;

          if (!this.history.has(key)) this.history.set(key, []);
          const arr = this.history.get(key);
          arr.push({ x: cx, y: cy, camId: String(camId), frame: this.frameIdx });
          if (arr.length > this.HISTORY_LEN) arr.shift();

          this.lastSeen.set(key, this.frameIdx);

          this.drawDot(key, cx, cy, key);
          drawn += 1;
        }
      }

      // TTL 지난 트랙 제거
      for (const [key, last] of this.lastSeen.entries()) {
        if (this.frameIdx - last > this.TTL_FRAMES) {
          this.lastSeen.delete(key);
          this.history.delete(key);
        }
      }

      this.redrawTrails();

      if (drawn === 0) {
        console.warn("No points drawn. Sample data:", data);
      }
    }
  }

  global.BEVRenderer = BEVRenderer;
})(window);
