package com.example.edgecam

import android.Manifest
import android.os.Bundle
import android.util.Log
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import androidx.compose.ui.viewinterop.AndroidView

import com.example.edgecam.stream.RtspPublisher
import com.pedro.library.view.OpenGlView
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
    private val rtspHostUrl = "rtsp://10.100.0.21:8554/cam0"// 백엔드 원격 서버
    private val camId = 0
    private val token = "dev-token-cam0" // 유효 접속 인증용 토큰 (camId별로 맞추기, 사용자 입력으로 결정할 수 있는 기능 추가 필요)

    private var seq: Long = 0L

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        setContent {
            MaterialTheme {
                RtspStreamScreen(rtspHostUrl)
            }
        }

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

@Composable
private fun RtspStreamScreen(rtspUrl: String) {
    val ctx = LocalContext.current

    var status by remember { mutableStateOf("idle") }
    val publisher = remember {
        RtspPublisher(ctx) { msg -> status = msg }
    }

    // 권한 요청 (카메라 + 오디오)
    val permissionLauncher = rememberLauncherForActivityResult(
        ActivityResultContracts.RequestMultiplePermissions()
    ) { result ->
        val camOk = result[Manifest.permission.CAMERA] == true
        val micOk = result[Manifest.permission.RECORD_AUDIO] == true
        status = "perm camera=$camOk mic=$micOk"
    }

    // 화면에 들어오자마자 권한 요청
    LaunchedEffect(Unit) {
        permissionLauncher.launch(
            arrayOf(
                Manifest.permission.CAMERA,
                Manifest.permission.RECORD_AUDIO
            )
        )
    }

    DisposableEffect(Unit) {
        onDispose { publisher.release() }
    }

    Column(Modifier.fillMaxSize().padding(12.dp)) {
        Text("RTSP Status: $status")

        Spacer(Modifier.height(8.dp))

        // 카메라 프리뷰 (OpenGlView)
        AndroidView(
            modifier = Modifier
                .fillMaxWidth()
                .height(300.dp),
            factory = { context ->
                OpenGlView(context).apply {
                    keepScreenOn = true
                }
            },
            update = { glView ->
                // glView가 생길 때 한 번 바인딩
                publisher.bindPreview(glView) // 여기선 바인딩만
                //publisher.startPreview()
            }
        )

        Spacer(Modifier.height(12.dp))

        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Button(onClick = { // 버튼을 누를때
                publisher.startPreview() //preview와 stream을 같이 시작
                publisher.startStream(rtspUrl) }) {
                Text("Start RTSP")
            }
            OutlinedButton(onClick = { publisher.stopStream() }) {
                Text("Stop RTSP")
            }
        }
    }
}