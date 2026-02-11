package com.example.edgecam.util

import android.util.Base64
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

    fun packFloat16Base64(emb: FloatArray, normalize: Boolean = true): String {
        if (normalize) l2NormalizeInPlace(emb)

        val buf = ByteBuffer.allocate(emb.size * 2).order(ByteOrder.LITTLE_ENDIAN)
        for (f in emb) {
            buf.putShort(floatToHalfBits(f))
        }
        return Base64.encodeToString(buf.array(), Base64.NO_WRAP)
    }

    /**
     * float32 -> IEEE754 float16 bits (round-to-nearest-even 근사)
     * - NaN/Inf 처리 포함
     * - subnormal 간단 처리 포함
     */
    private fun floatToHalfBits(f: Float): Short {
        val bits = java.lang.Float.floatToIntBits(f)
        val sign = (bits ushr 16) and 0x8000
        var exp = ((bits ushr 23) and 0xFF)
        var mant = bits and 0x7FFFFF

        // NaN / Inf
        if (exp == 0xFF) {
            return (sign or 0x7C00 or (if (mant != 0) 0x01 else 0x00)).toShort()
        }

        // exponent adjust: float32 bias 127 -> float16 bias 15
        exp = exp - 127 + 15

        // underflow -> subnormal/zero
        if (exp <= 0) {
            if (exp < -10) {
                return sign.toShort() // too small -> 0
            }
            // subnormal: implicit leading 1 for mantissa in float32
            mant = mant or 0x800000
            val shift = 1 - exp
            // round
            val halfMant = (mant ushr (13 + shift))
            return (sign or halfMant).toShort()
        }

        // overflow -> Inf
        if (exp >= 0x1F) {
            return (sign or 0x7C00).toShort()
        }

        // normal
        // round mantissa: take top 10 bits with rounding
        val mantRounded = mant + 0x1000 // rounding bias for 13-bit shift
        val halfMant = (mantRounded ushr 13) and 0x03FF

        return (sign or (exp shl 10) or halfMant).toShort()
    }

    /** float16 payload bytes size for given dim */
    fun float16Bytes(dim: Int): Int = dim * 2

    /**
     * Rough estimate: Base64 expands by ~4/3 plus padding.
     * For accurate measure: use b64.length in chars (ASCII) == bytes count in UTF-8.
     */
    fun estimateBase64Len(bytesLen: Int): Int = ((bytesLen + 2) / 3) * 4


}
