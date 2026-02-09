import android.util.Base64
import android.util.Half
import java.nio.ByteBuffer
import java.nio.ByteOrder
import kotlin.math.sqrt

object EmbeddingPacker {

    /**
     * 요구사항: API 26+ (Galaxy S24는 OK) 
     * android.util.Half를 사용해 float→half 변환(IEEE 754 half) 진행
     * FloatArray(float32) -> float16 raw bytes (little-endian) -> base64 (NO_WRAP)
     *
     * 서버(python)는:
     * raw = base64.b64decode(emb_b64)
     * np.frombuffer(raw, dtype=np.float16).astype(np.float32)
     * 로 읽게 됩니다.
     */
    /** L2 normalize: emb / ||emb|| (norm==0이면 원본 그대로 반환) */
    fun l2NormalizeInPlace(emb: FloatArray): FloatArray {
        var ss = 0.0
        for (v in emb) ss += (v * v).toDouble()
        val norm = sqrt(ss).toFloat()
        if (norm <= 1e-12f) return emb
        for (i in emb.indices) emb[i] = emb[i] / norm
        return emb
    }
    fun packFloat16Base64(emb: FloatArray): String {
        /**
         * FloatArray(float32) -> float16 raw bytes (little-endian) -> base64(NO_WRAP)
         * return: base64 string
         */
         // float16(half) = 2 bytes per element
        if (normalize) l2NormalizeInPlace(emb)
        val buf = ByteBuffer.allocate(emb.size * 2).order(ByteOrder.LITTLE_ENDIAN) //LITTLE_ENDIAN -> 파이썬 np.float16과 가장 안전하게 맞추기 위함
        for (f in emb) {
            val halfBits: Short = Half.toHalf(f) // IEEE 754 half bits
            buf.putShort(halfBits)
        }
        val bytes = buf.array()
        return Base64.encodeToString(bytes, Base64.NO_WRAP) // NO_WRAP: 줄바꿈 문자 없는 스트링(서버 파싱 안정적)
    }
    /** float16 payload bytes size for given dim */
    fun float16Bytes(dim: Int): Int = dim * 2

    /**
     * Rough estimate: Base64 expands by ~4/3 plus padding.
     * For accurate measure: use b64.length in chars (ASCII) == bytes count in UTF-8.
     */
    fun estimateBase64Len(bytesLen: Int): Int = ((bytesLen + 2) / 3) * 4
        
    /**
     * (디버그용) base64 float16 -> FloatArray(float32) 복원
     */
    fun unpackFloat16Base64(b64: String, dim: Int): FloatArray {
        val raw = Base64.decode(b64, Base64.DEFAULT)
        require(raw.size == dim * 2) { "Invalid byte length: ${raw.size}, expected ${dim * 2}" }

        val buf = ByteBuffer.wrap(raw).order(ByteOrder.LITTLE_ENDIAN)
        val out = FloatArray(dim)
        for (i in 0 until dim) {
            val halfBits = buf.getShort()
            out[i] = Half.toFloat(halfBits)
        }
        return out
    }
}
