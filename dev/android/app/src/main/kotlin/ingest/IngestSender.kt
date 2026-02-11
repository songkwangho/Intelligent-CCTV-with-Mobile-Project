package com.example.edgecam.ingest

import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.Response
import okhttp3.WebSocket
import okhttp3.WebSocketListener
import java.util.concurrent.atomic.AtomicBoolean

class IngestSender(
    private val serverHostPort: String, // 예: "10.0.2.2:8001" 또는 "192.168.0.10:8001"
    private val camId: Int,
    private val token: String,
) {
    private val client = OkHttpClient()
    private var ws: WebSocket? = null
    private val connected = AtomicBoolean(false)

    fun connect() {
        val url = "ws://$serverHostPort/ingest/$camId"
        val req = Request.Builder().url(url).addHeader("X-Edge-Token", token).build()

        ws = client.newWebSocket(req, object : WebSocketListener() {
            override fun onOpen(webSocket: WebSocket, response: Response) {
                connected.set(true)
            }

            override fun onFailure(webSocket: WebSocket, t: Throwable, response: Response?) {
                connected.set(false)
                android.util.Log.e("EdgeCam", "ws failure: ${t.javaClass.simpleName}: ${t.message}", t)
                if (response != null) {
                    android.util.Log.e("EdgeCam", "ws failure response: code=${response.code} msg=${response.message}")
                }
            }

            override fun onClosing(webSocket: WebSocket, code: Int, reason: String) {
                connected.set(false)
                webSocket.close(code, reason)
            }

            override fun onClosed(webSocket: WebSocket, code: Int, reason: String) {
                connected.set(false)
            }
        })
    }

    fun isConnected(): Boolean = connected.get()

    fun send(jsonStr: String): Boolean {
        val s = ws ?: return false
        return s.send(jsonStr)
    }

    fun close() {
        ws?.close(1000, "bye")
        ws = null
        connected.set(false)
    }
}
