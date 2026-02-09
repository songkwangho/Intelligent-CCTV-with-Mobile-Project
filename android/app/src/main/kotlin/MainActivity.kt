package com.example.edgecam

import android.os.Bundle
import android.util.Log
import androidx.activity.ComponentActivity

import com.example.edgecam.ingest.IngestMessageBuilder
import com.example.edgecam.ingest.IngestSender

import kotlinx.coroutines.*
import org.json.JSONObject
import kotlin.math.sin
import kotlin.random.Random

class MainActivity : ComponentActivity() {

    private var job: Job? = null
    private lateinit var sender: IngestSender

    private val serverHostPort = "10.100.0.21:8001"// 백엔드 원격 서버
    private val camId = 0
    private val token = "dev-token-cam0" // 유효 접속 인증용 토큰 (camId별로 맞추기, 사용자 입력으로 결정할 수 있는 기능 추가 필요)

    private var seq: Long = 0L

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        sender = IngestSender(serverHostPort, camId, token)
        sender.connect()

        job = CoroutineScope(Dispatchers.IO).launch {
            var frameId = 0L
            val people = listOf(80f to 80f, 120f to 120f, 160f to 160f) // 3명 목업 사람 (모델이 탐지하는 기능 추가시 삭제)

            while (isActive) {
                frameId += 1
                seq += 1

                val tsSec = System.currentTimeMillis() / 1000.0
                val captureTsUs = System.currentTimeMillis() * 1000L

                val dets = ArrayList<JSONObject>(people.size)
                for ((i, p) in people.withIndex()) {
                    val (bx, by) = p
                    val x = bx + (sin((frameId + i) * 0.1) * 5.0).toFloat() + Random.nextFloat() * 0.5f
                    val y = by + (sin((frameId + i) * 0.12) * 5.0).toFloat() + Random.nextFloat() * 0.5f

                    val emb = makeDummyEmbedding128(camId * 100 + i)// 3명 목업 사람 (모델이 추출하는 기능 추가시 삭제)

                    dets.add(
                        IngestMessageBuilder.buildDetectionJsonBev(
                            bevX = x,
                            bevY = y,
                            embedding = emb,
                            dimExpected = 128
                        )
                    )
                }

                val built = IngestMessageBuilder.buildIngestMsg( v = 1, tsSec = tsSec, frameId = frameId, seq = seq,
                    captureTsUs = captureTsUs, detections = dets)

                val ok = sender.send(built.json)
                Log.i("EdgeCam", "send ok=$ok connected=${sender.isConnected()} bytes=${built.byteSize} dets=${built.detectionsCount}")

                delay(100)
            }
        }
    }

    override fun onDestroy() {
        job?.cancel()
        sender.close()
        super.onDestroy()
    }

    private fun makeDummyEmbedding128(seed: Int): FloatArray {
        val r = Random(seed)
        return FloatArray(128) { (r.nextFloat() * 2f) - 1f }
    }
}
