package com.example.edgecam.ingest

import com.example.edgecam.util.EmbeddingPacker
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
            put("bev_x", bevX)
            put("bev_y", bevY)
            put("emb_b64", b64)
            put("emb_dtype", "float16")
        }
    }

    fun buildIngestMsg(
        v: Int = 1,
        tsSec: Double,     // edge send time (sec)
        frameId: Long,
        seq: Long,         // per-camera increasing sequence
        captureTsUs: Long, // capture timestamp in microseconds (key for video sync)
        detections: List<JSONObject>
    ): BuiltMessage {
        val arr = JSONArray()
        detections.forEach { arr.put(it) }

        val msg = JSONObject().apply {
            put("v", v)
            put("ts", tsSec)
            put("frame_id", frameId)
            put("seq", seq)
            put("capture_ts_us", captureTsUs)
            put("detections", arr)
        }

        val jsonStr = msg.toString()
        val bytes = jsonStr.toByteArray(StandardCharsets.UTF_8)

        return BuiltMessage(
            json = jsonStr,
            byteSize = bytes.size,
            detectionsCount = detections.size
        )
    }
}