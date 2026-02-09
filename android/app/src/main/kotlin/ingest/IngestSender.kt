import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.WebSocket
import okhttp3.WebSocketListener

class IngestSender(
    private val serverHost: String, // e.g. "192.168.0.10:8001"
    private val camId: Int
) {
    private val client = OkHttpClient()
    private var ws: WebSocket? = null

    fun connect() {
        val url = "ws://$serverHost/ingest/$camId"
        val request = Request.Builder().url(url).build()

        ws = client.newWebSocket(request, object : WebSocketListener() {
            override fun onOpen(webSocket: WebSocket, response: okhttp3.Response) {
                // connected
            }
            override fun onFailure(webSocket: WebSocket, t: Throwable, response: okhttp3.Response?) {
                // handle reconnect outside if needed
            }
        })
    }

    fun send(jsonStr: String) {
        ws?.send(jsonStr)
    }

    fun close() {
        ws?.close(1000, "bye")
        ws = null
    }
}
