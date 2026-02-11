package com.example.edgecam.stream

import android.content.Context
import android.util.Log
import com.pedro.common.ConnectChecker
import com.pedro.library.rtsp.RtspCamera2
import com.pedro.library.view.OpenGlView

class RtspPublisher(
    context: Context,
    private val onStatus: (String) -> Unit = {}
) {

    private val tag = "RtspPublisher"

    private val connectChecker = object : ConnectChecker {
        override fun onConnectionStarted(url: String) {
            Log.i(tag, "onConnectionStarted: $url")
            onStatus("RTSP connecting: $url")
        }

        override fun onConnectionSuccess() {
            Log.i(tag, "onConnectionSuccess")
            onStatus("RTSP connected")
        }

        override fun onConnectionFailed(reason: String) {
            Log.w(tag, "onConnectionFailed: $reason")
            onStatus("RTSP failed: $reason")
        }

        override fun onDisconnect() {
            Log.i(tag, "onDisconnect")
            onStatus("RTSP disconnected")
        }

        override fun onAuthError() {
            Log.w(tag, "onAuthError")
            onStatus("RTSP auth error")
        }

        override fun onAuthSuccess() {
            Log.i(tag, "onAuthSuccess")
            onStatus("RTSP auth success")
        }

        override fun onNewBitrate(bitrate: Long) {
            // optional
            // onStatus("bitrate=$bitrate")
        }
    }

    // RtspCamera2는 preview surface(OpenGlView/SurfaceView 등)가 필요
    private var camera: RtspCamera2? = null

    private var bound = false
    fun bindPreview(openGlView: OpenGlView) {
        /** Compose의 AndroidView로 만든 OpenGlView를 붙인다 */
        if (bound) return
        camera = RtspCamera2(openGlView, connectChecker)
        bound = true
    }
    fun startPreview() {
        val cam = camera ?: run {
            onStatus("preview not bound")
            return
        }
        if (!cam.isOnPreview) {
            cam.startPreview()
            onStatus("preview started")
        }
    }
    fun startPreviewWhenReady() {
        val cam = camera ?: run {
            onStatus("preview not bound")
            return
        }
        val gl = cam.glInterface as? com.pedro.library.view.OpenGlView
        if (gl != null) {
            gl.holder.addCallback(object : android.view.SurfaceHolder.Callback {
                override fun surfaceCreated(holder: android.view.SurfaceHolder) {
                    try {
                        if (!cam.isOnPreview) {
                            cam.startPreview()
                            onStatus("preview started")
                        }
                    } catch (t: Throwable) {
                        onStatus("preview error: ${t.message}")
                    }
                    gl.holder.removeCallback(this)
                }
                override fun surfaceChanged(holder: android.view.SurfaceHolder, format: Int, width: Int, height: Int) {}
                override fun surfaceDestroyed(holder: android.view.SurfaceHolder) {}
            })
            onStatus("waiting surface...")
        } else {
            // fallback
            cam.startPreview()
            onStatus("preview started (fallback)")
        }
    }
    fun stopPreview() {
        val cam = camera ?: return
        if (cam.isOnPreview) cam.stopPreview()
    }

    /**
     * @param url ex) rtsp://10.100.0.21:8554/cam0
     */
    fun startStream(url: String) {
        val cam = camera ?: run {
            onStatus("preview not bound")
            return
        }

        // 최소 성공 세팅: 1280x720, 30fps, 2Mbps 정도
        // OpenGlView 사용 시 하드웨어 회전 옵션 관련 주의가 문서에 있음. :contentReference[oaicite:1]{index=1}
        val videoOk = cam.prepareVideo(1280, 720, 30, 2_000_000,2, 0)

        val audioOk = false // 오디오 필요 없으면 false로 두고 아래에서 onlyVideo로 운영해도 됨
        // val audioOk = cam.prepareAudio() // 오디오 필요 없으면 false로 두고 아래에서 onlyVideo로 운영해도 됨

        if (!videoOk) {
            onStatus("prepareVideo failed")
            return
        }
        if (!audioOk) {
            // 오디오 준비 실패여도 영상만 보내고 싶다면 계속 진행 가능
            onStatus("prepareAudio failed (video-only will still try)")
            cam.getStreamClient().setOnlyVideo(true)
        }

        if (!cam.isStreaming) {
            cam.startStream(url)
            onStatus("stream start requested")
        } else {
            onStatus("already streaming")
        }
    }

    fun stopStream() {
        val cam = camera ?: return
        if (cam.isStreaming) {
            cam.stopStream()
            onStatus("stream stopped")
        }
    }

    fun release() {
        try {
            stopStream()
            stopPreview()
        } catch (_: Throwable) {
        }
        camera = null
    }
}

private fun RtspCamera2.prepareVideo(
    width: Int,
    height: Int,
    fps: Int,
    bitrate: Int,
    iFrameInterval: Boolean,
    rotation: Int
) {
}
