val sender = IngestSender("127.0.0.1:8001", camId = 0)
sender.connect()

val built = IngestMessageBuilder.buildIngestMsg(
    tsSec = System.currentTimeMillis() / 1000.0,
    frameId = frameId,
    detections = dets
)
println("ingest payload bytes=${built.byteSize}, dets=${built.detectionsCount}")
sender.send(built.json)

val emb = FloatArray(128) { i -> (i - 64) / 64f } // 예시(실제로는 ReID 출력)
val det = buildDetectionJson(bevX = 120.1f, bevY = 33.2f, embedding128 = emb)
val msg = buildIngestMsg(camId = 0, frameId = 1, tsSec = System.currentTimeMillis() / 1000.0, detections = listOf(det))

sender.send(msg)


