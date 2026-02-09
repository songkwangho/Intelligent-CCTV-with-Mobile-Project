// frontend/main.js
(function () {
  console.log("[main.js] loaded"); // 로드 확인용

  const statusEl = document.getElementById("status");
  const setStatus = (s) => {
    if (statusEl) statusEl.textContent = `status: ${s}`;
  };

  const cfg = window.APP_CONFIG || {};
  const wsUrl = cfg.wsUrl || "ws://127.0.0.1:8001/ws";
  setStatus(`connecting -> ${wsUrl}`);

  const bg = document.getElementById("bg");
  const trail = document.getElementById("trail");
  const dot = document.getElementById("dot");

  if (!bg || !trail || !dot) {
    console.error("Canvas elements not found. Check index.html ids.");
    setStatus("error: canvas elements not found");
    return;
  }

  if (!window.BEVRenderer) {
    console.error("BEVRenderer is not defined. canvas.js not loaded?");
    setStatus("error: BEVRenderer missing");
    return;
  }

  const renderer = new window.BEVRenderer(bg, trail, dot, {
    historyLen: cfg.historyLen ?? 50,
    ttlFrames: cfg.ttlFrames ?? 15,
    jumpThPx: cfg.jumpThPx ?? 80,
    gapFrames: cfg.gapFrames ?? 2,
    breakOnCamChange: cfg.breakOnCamChange ?? true,
  });

  const ws = new WebSocket(wsUrl);

  ws.onopen = () => {
    console.log("WebSocket connected:", wsUrl);
    setStatus(`connected -> ${wsUrl}`);
  };

  ws.onerror = (e) => {
    console.error("WebSocket error:", e);
    setStatus("error: websocket");
  };

  ws.onclose = (e) => {
    console.log("WebSocket closed:", e.code, e.reason);
    setStatus(`closed: ${e.code} ${e.reason || ""}`);
  };

  ws.onmessage = (event) => {
    let msg;
    try {
      msg = JSON.parse(event.data);
    } catch (e) {
      console.error("Bad JSON:", event.data);
      return;
    }

    // 메시지 타입 확인용 (너무 많으면 주석 처리)
    // console.log("[ws] type:", msg.type);

    if (msg.type === "camera_init") {
      renderer.renderCameraInit(msg.cameras);
      setStatus("receiving: camera_init");
      return;
    }

    if (msg.type === "detected_data") {
      renderer.renderDetectedData(msg.data || {});
      setStatus("receiving: detected_data");
      return;
    }

    if (msg.type === "camera_status") {// msg.status: { "0": {online, rx_fps, ...}, "1": {...} }
      console.log("camera_status", msg.status);
    }

  };
})();
