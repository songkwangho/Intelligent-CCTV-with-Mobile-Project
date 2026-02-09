import org.json.JSONArray
import org.json.JSONObject
import java.nio.charset.StandardCharsets

object IngestMessageBuilder {

    data class BuiltMessage(
        val json: String,
        val byteSize: Int,         // UTF-8 bytes
        val detectionsCount: Int
    )

    fun buildDetectionJsonBev(
        bevX: Float,
        bevY: Float,
        embedding: FloatArray,
        dimExpected: Int = 128
    ): JSONObject {
        require(embedding.size == dimExpected) {
            "Embedding dim mismatch: ${embedding.size} != $dimExpected"
        }

        val b64 = EmbeddingPacker.packFloat16Base64(embedding, normalize = true)

        return JSONObject().apply {
            put("bev_x", bevX)// 지금 PoC 기준: bev_x/ bev_y 또는 x/y 
            put("bev_y", bevY)
            put("emb_b64", b64)// ✅ float16 base64
            put("emb_dtype", "float16") // ✅ 서버 파서가 이걸 보고 np.float16 처리
        // put("conf", 0.92)            // 옵션
        // put("bbox", ...)             // 옵션(2단계에서)
        // put("foot", ...)             // 옵션(2단계에서)
        }
    }

    fun buildIngestMsg(
        v: Int = 1,
        tsSec: Double,
        frameId: Long,
        detections: List<JSONObject>
    ): BuiltMessage {
        val arr = JSONArray()
        detections.forEach { arr.put(it) }

        val msg = JSONObject().apply {
            put("v", v)
            put("ts", tsSec)
            put("frame_id", frameId)
            put("detections", arr)
        }

        val jsonStr = msg.toString()
        val bytes = jsonStr.toByteArray(StandardCharsets.UTF_8)
        return BuiltMessage(json = jsonStr, byteSize = bytes.size, detectionsCount = detections.size)
    }
}
