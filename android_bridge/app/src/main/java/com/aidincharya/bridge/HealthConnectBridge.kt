package com.aidincharya.bridge

import android.content.Context
import android.util.Log
import androidx.health.connect.client.HealthConnectClient
import androidx.health.connect.client.permission.HealthPermission
import androidx.health.connect.client.records.HeartRateRecord
import androidx.health.connect.client.records.OxygenSaturationRecord
import androidx.health.connect.client.records.SleepSessionRecord
import androidx.health.connect.client.records.StepsRecord
import androidx.health.connect.client.request.ReadRecordsRequest
import androidx.health.connect.client.time.TimeRangeFilter
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import org.json.JSONArray
import org.json.JSONObject
import java.time.Duration
import java.time.Instant
import java.time.temporal.ChronoUnit
import java.util.concurrent.TimeUnit

data class SyncResult(
    val success: Boolean,
    val recordsFoundCount: Int,
    val hrCount: Int,
    val stepsCount: Int,
    val spo2Count: Int,
    val sleepCount: Int = 0,
    val sleepDurationHours: Double = 0.0,
    val sourcePackage: String,
    val serverAcceptedCount: Int,
    val serverDuplicateCount: Int,
    val latestMeasurementTimestamp: Double = 0.0,
    val isUpstreamStale: Boolean = false,
    val newRecordsObserved: Boolean = false,
    val message: String,
    val details: String
)

class HealthConnectBridge(private val context: Context) {

    private val client by lazy {
        if (isHealthConnectAvailable()) HealthConnectClient.getOrCreate(context) else null
    }

    private val httpClient = OkHttpClient.Builder()
        .connectTimeout(15, TimeUnit.SECONDS)
        .readTimeout(20, TimeUnit.SECONDS)
        .writeTimeout(20, TimeUnit.SECONDS)
        .build()

    companion object {
        val REQUIRED_PERMISSIONS = setOf(
            HealthPermission.getReadPermission(HeartRateRecord::class),
            HealthPermission.getReadPermission(StepsRecord::class),
            HealthPermission.getReadPermission(OxygenSaturationRecord::class),
            HealthPermission.getReadPermission(SleepSessionRecord::class)
        )
        // Global sync mutex to ensure foreground loops, background workers, and manual buttons never execute concurrently
        private val syncMutex = kotlinx.coroutines.sync.Mutex()
    }

    fun isHealthConnectAvailable(): Boolean {
        val status = HealthConnectClient.getSdkStatus(context)
        return status == HealthConnectClient.SDK_AVAILABLE
    }

    suspend fun getGrantedPermissions(): Set<String> {
        val hcClient = client ?: return emptySet()
        return withContext(Dispatchers.IO) {
            try {
                hcClient.permissionController.getGrantedPermissions()
            } catch (e: Exception) {
                emptySet()
            }
        }
    }

    suspend fun hasAllPermissions(): Boolean {
        val granted = getGrantedPermissions()
        return REQUIRED_PERMISSIONS.all { it in granted }
    }

    /**
     * Reads genuine records from Health Connect using watermark-bounded windowing
     * with late-arrival overlap and transmits them to the backend idempotently.
     */
    suspend fun syncWearableData(
        serverBaseUrl: String,
        authToken: String
    ): SyncResult = withContext(Dispatchers.IO) {
        // Concurrency Guard: prevent concurrent/overlapping sync executions
        if (!syncMutex.tryLock()) {
            return@withContext SyncResult(
                success = false,
                recordsFoundCount = 0,
                hrCount = 0,
                stepsCount = 0,
                spo2Count = 0,
                sourcePackage = "coordinator",
                serverAcceptedCount = 0,
                serverDuplicateCount = 0,
                message = "Synchronization already in progress. Skipping overlapping run.",
                details = "Synchronization coordinator prevented concurrent network/DB execution."
            )
        }

        try {
            val hcClient = client ?: return@withContext SyncResult(
                success = false,
                recordsFoundCount = 0,
                hrCount = 0,
                stepsCount = 0,
                spo2Count = 0,
                sourcePackage = "unknown",
                serverAcceptedCount = 0,
                serverDuplicateCount = 0,
                message = "Health Connect SDK not available on this device.",
                details = "Please ensure Health Connect is installed and updated via Google Play."
            )

            val granted = getGrantedPermissions()
            val missing = REQUIRED_PERMISSIONS.filter { it !in granted }
            if (missing.isNotEmpty()) {
                return@withContext SyncResult(
                    success = false,
                    recordsFoundCount = 0,
                    hrCount = 0,
                    stepsCount = 0,
                    spo2Count = 0,
                    sourcePackage = "unknown",
                    serverAcceptedCount = 0,
                    serverDuplicateCount = 0,
                    message = "Missing Health Connect permissions: ${missing.joinToString()}",
                    details = "Please grant Activity and Vitals permissions to proceed."
                )
            }

            // Watermarking & Bounded Incremental Windowing
            val prefs = context.getSharedPreferences("aidincharya_prefs", Context.MODE_PRIVATE)
            val lastWatermarkMs = prefs.getLong("last_sync_watermark_ms", 0L)
            val lastSeenMeasurementTs = prefs.getFloat("last_seen_measurement_ts", 0f).toDouble()

            val now = Instant.now()
            // Bounded window: use previous watermark minus 10-minute overlap window for late-arriving records
            val startTime = if (lastWatermarkMs > 0L) {
                val watermarkInstant = Instant.ofEpochMilli(lastWatermarkMs)
                val overlapStart = watermarkInstant.minus(10, ChronoUnit.MINUTES)
                val maxHistoryStart = now.minus(24, ChronoUnit.HOURS)
                if (overlapStart.isBefore(maxHistoryStart)) maxHistoryStart else overlapStart
            } else {
                now.minus(24, ChronoUnit.HOURS)
            }
            val timeFilter = TimeRangeFilter.between(startTime, now)

            val discreteRecordsJson = JSONArray()
            var latestHrVal: Double? = null
            var totalSteps = 0L
            var latestSpo2Val: Double? = null
            var detectedSourcePackage = "com.fastrack.smartworld"
            var latestTimestamp = (now.toEpochMilli() / 1000.0)
            var maxObservedMeasurementTs = 0.0

        var hrFound = 0
        var stepsFound = 0
        var spo2Found = 0
        var sleepFound = 0
        var latestSleepDurationHours = 0.0
        var latestSleepRecord: JSONObject? = null

        try {
            // 1. Read Heart Rate records
            val hrResponse = hcClient.readRecords(
                ReadRecordsRequest(
                    recordType = HeartRateRecord::class,
                    timeRangeFilter = timeFilter
                )
            )
            for (record in hrResponse.records) {
                val pkg = record.metadata.dataOrigin.packageName
                if (pkg.isNotEmpty() && !pkg.contains("healthdata")) {
                    detectedSourcePackage = pkg
                }
                for (sample in record.samples) {
                    hrFound++
                    val bpm = sample.beatsPerMinute.toDouble()
                    latestHrVal = bpm
                    val sampleTs = sample.time.epochSecond.toDouble()
                    if (sampleTs > maxObservedMeasurementTs) {
                        maxObservedMeasurementTs = sampleTs
                    }
                    if (sampleTs > latestTimestamp || latestTimestamp == (now.toEpochMilli() / 1000.0)) {
                        latestTimestamp = sampleTs
                    }
                    val recObj = JSONObject().apply {
                        put("record_id", "${record.metadata.id}_${sample.time.toEpochMilli()}")
                        put("metric_type", "heart_rate")
                        put("value", bpm)
                        put("unit", "bpm")
                        put("timestamp", sampleTs)
                        put("source_package", pkg)
                        put("device_model", "Fastrack Noir Charm")
                        put("acquisition_method", "health_connect_import")
                    }
                    discreteRecordsJson.put(recObj)
                }
            }

            // 2. Read Steps records
            val stepsResponse = hcClient.readRecords(
                ReadRecordsRequest(
                    recordType = StepsRecord::class,
                    timeRangeFilter = timeFilter
                )
            )
            for (record in stepsResponse.records) {
                stepsFound++
                totalSteps += record.count
                val pkg = record.metadata.dataOrigin.packageName
                if (pkg.isNotEmpty() && !pkg.contains("healthdata")) {
                    detectedSourcePackage = pkg
                }
                val stepTs = record.endTime.epochSecond.toDouble()
                if (stepTs > maxObservedMeasurementTs) {
                    maxObservedMeasurementTs = stepTs
                }
                val recObj = JSONObject().apply {
                    put("record_id", record.metadata.id)
                    put("metric_type", "steps")
                    put("value", record.count.toDouble())
                    put("unit", "count")
                    put("timestamp", stepTs)
                    put("source_package", pkg)
                    put("device_model", "Fastrack Noir Charm")
                    put("acquisition_method", "health_connect_import")
                }
                discreteRecordsJson.put(recObj)
            }

            // 3. Read Oxygen Saturation (SpO2) records
            val spo2Response = hcClient.readRecords(
                ReadRecordsRequest(
                    recordType = OxygenSaturationRecord::class,
                    timeRangeFilter = timeFilter
                )
            )
            for (record in spo2Response.records) {
                spo2Found++
                val pct = record.percentage.value
                latestSpo2Val = pct
                val pkg = record.metadata.dataOrigin.packageName
                if (pkg.isNotEmpty() && !pkg.contains("healthdata")) {
                    detectedSourcePackage = pkg
                }
                val spo2Ts = record.time.epochSecond.toDouble()
                if (spo2Ts > maxObservedMeasurementTs) maxObservedMeasurementTs = spo2Ts
                val recObj = JSONObject().apply {
                    put("record_id", record.metadata.id)
                    put("metric_type", "spo2")
                    put("value", pct)
                    put("unit", "%")
                    put("timestamp", spo2Ts)
                    put("source_package", pkg)
                    put("device_model", "Fastrack Noir Charm")
                    put("acquisition_method", "health_connect_import")
                }
                discreteRecordsJson.put(recObj)
            }

            // 4. Read SleepSessionRecord (using 48-hour rolling window for complete overnight cycles crossing midnight)
            val sleepTimeFilter = TimeRangeFilter.between(now.minus(48, ChronoUnit.HOURS), now)
            val sleepResponse = hcClient.readRecords(
                ReadRecordsRequest(
                    recordType = SleepSessionRecord::class,
                    timeRangeFilter = sleepTimeFilter
                )
            )
            for (record in sleepResponse.records) {
                sleepFound++
                val pkg = record.metadata.dataOrigin.packageName
                if (pkg.isNotEmpty() && !pkg.contains("healthdata")) {
                    detectedSourcePackage = pkg
                }
                val startTs = record.startTime.epochSecond.toDouble()
                val endTs = record.endTime.epochSecond.toDouble()
                val durationSec = Duration.between(record.startTime, record.endTime).seconds
                val durationHours = durationSec / 3600.0
                latestSleepDurationHours = durationHours

                if (endTs > maxObservedMeasurementTs) {
                    maxObservedMeasurementTs = endTs
                }

                var deepSleepSec = 0L
                var lightSleepSec = 0L
                var remSleepSec = 0L
                var awakeSec = 0L

                val stagesArray = JSONArray()
                for (stage in record.stages) {
                    val sStart = stage.startTime.epochSecond.toDouble()
                    val sEnd = stage.endTime.epochSecond.toDouble()
                    val sDur = Duration.between(stage.startTime, stage.endTime).seconds
                    val stageName = when (stage.stage) {
                        SleepSessionRecord.STAGE_TYPE_DEEP -> {
                            deepSleepSec += sDur
                            "deep"
                        }
                        SleepSessionRecord.STAGE_TYPE_LIGHT -> {
                            lightSleepSec += sDur
                            "light"
                        }
                        SleepSessionRecord.STAGE_TYPE_REM -> {
                            remSleepSec += sDur
                            "rem"
                        }
                        SleepSessionRecord.STAGE_TYPE_AWAKE -> {
                            awakeSec += sDur
                            "awake"
                        }
                        SleepSessionRecord.STAGE_TYPE_OUT_OF_BED -> {
                            awakeSec += sDur
                            "out_of_bed"
                        }
                        SleepSessionRecord.STAGE_TYPE_SLEEPING -> {
                            lightSleepSec += sDur
                            "sleeping"
                        }
                        else -> "unknown"
                    }
                    stagesArray.put(JSONObject().apply {
                        put("stage", stageName)
                        put("start_time", sStart)
                        put("end_time", sEnd)
                        put("duration_seconds", sDur)
                    })
                }

                val recObj = JSONObject().apply {
                    put("record_id", record.metadata.id)
                    put("metric_type", "sleep")
                    put("value", durationHours)
                    put("unit", "hours")
                    put("timestamp", endTs)
                    put("start_time", startTs)
                    put("end_time", endTs)
                    put("source_package", pkg)
                    put("device_model", "Fastrack Noir Charm")
                    put("acquisition_method", "health_connect_import")
                    put("aggregation_type", "interval")
                    put("deep_sleep_hours", deepSleepSec / 3600.0)
                    put("light_sleep_hours", lightSleepSec / 3600.0)
                    put("rem_sleep_hours", remSleepSec / 3600.0)
                    put("awake_minutes", awakeSec / 60)
                    put("stages", stagesArray)
                }
                discreteRecordsJson.put(recObj)

                latestSleepRecord = JSONObject().apply {
                    put("duration_hours", durationHours)
                    put("start_timestamp", startTs)
                    put("end_timestamp", endTs)
                    put("deep_sleep_hours", deepSleepSec / 3600.0)
                    put("light_sleep_hours", lightSleepSec / 3600.0)
                    put("rem_sleep_hours", remSleepSec / 3600.0)
                    put("awake_minutes", awakeSec / 60)
                    put("source", pkg)
                }
            }

            Log.i("HealthConnectBridge", "Health Connect records read: hr=$hrFound, steps=$stepsFound, spo2=$spo2Found, sleep=$sleepFound from source=$detectedSourcePackage")

        } catch (e: Exception) {
            Log.e("HealthConnectBridge", "Failed reading from Health Connect: ${e.localizedMessage}", e)
            return@withContext SyncResult(
                success = false,
                recordsFoundCount = 0,
                hrCount = 0,
                stepsCount = 0,
                spo2Count = 0,
                sleepCount = 0,
                sleepDurationHours = 0.0,
                sourcePackage = "error",
                serverAcceptedCount = 0,
                serverDuplicateCount = 0,
                message = "Failed reading from Health Connect: ${e.localizedMessage}",
                details = e.stackTraceToString()
            )
        }

        val totalFound = hrFound + stepsFound + spo2Found + sleepFound
        val newRecordsObserved = maxObservedMeasurementTs > (lastSeenMeasurementTs + 1.0)
        val nowSec = now.epochSecond.toDouble()
        val ageSeconds = if (maxObservedMeasurementTs > 0.0) (nowSec - maxObservedMeasurementTs) else 86400.0
        val isUpstreamStale = ageSeconds > 1800.0 // > 30 minutes without fresh watch measurement

        if (totalFound == 0) {
            return@withContext SyncResult(
                success = true,
                recordsFoundCount = 0,
                hrCount = 0,
                stepsCount = 0,
                spo2Count = 0,
                sleepCount = 0,
                sleepDurationHours = 0.0,
                sourcePackage = detectedSourcePackage,
                serverAcceptedCount = 0,
                serverDuplicateCount = 0,
                latestMeasurementTimestamp = maxObservedMeasurementTs,
                isUpstreamStale = isUpstreamStale,
                newRecordsObserved = false,
                message = "No new wearable records in window (${startTime} to ${now}).",
                details = "Ensure Fastrack Smart World is actively paired with the Noir Charm and has synced its readings."
            )
        }

        // Construct payload conforming to AI Dincharya HealthConnectPayload contract
        val payload = JSONObject().apply {
            put("device_model", "Fastrack Noir Charm")
            put("source_package", detectedSourcePackage)
            put("recorded_at", if (maxObservedMeasurementTs > 0.0) maxObservedMeasurementTs else latestTimestamp)
            put("acquisition_method", "health_connect_import")
            latestHrVal?.let { put("heart_rate_bpm", it) }
            if (totalSteps > 0) put("steps", totalSteps)
            latestSpo2Val?.let { put("spo2_pct", it) }
            latestSleepRecord?.let { put("sleep", it) }
            put("records", discreteRecordsJson)
        }

        // Transmit to backend
        val cleanUrl = serverBaseUrl.trimEnd('/') + "/api/telemetry/health_connect"
        val requestBody = payload.toString().toRequestBody("application/json; charset=utf-8".toMediaType())
        val request = Request.Builder()
            .url(cleanUrl)
            .addHeader("Authorization", "Bearer $authToken")
            .addHeader("Content-Type", "application/json")
            .post(requestBody)
            .build()

        val networkResult = try {
            val response = httpClient.newCall(request).execute()
            val responseBody = response.body?.string() ?: ""

            if (!response.isSuccessful) {
                SyncResult(
                    success = false,
                    recordsFoundCount = totalFound,
                    hrCount = hrFound,
                    stepsCount = stepsFound,
                    spo2Count = spo2Found,
                    sleepCount = sleepFound,
                    sleepDurationHours = latestSleepDurationHours,
                    sourcePackage = detectedSourcePackage,
                    serverAcceptedCount = 0,
                    serverDuplicateCount = 0,
                    latestMeasurementTimestamp = maxObservedMeasurementTs,
                    isUpstreamStale = isUpstreamStale,
                    newRecordsObserved = newRecordsObserved,
                    message = "Server rejected sync: HTTP ${response.code}",
                    details = responseBody
                )
            } else {
                val respJson = JSONObject(responseBody)
                val inserted = respJson.optInt("inserted_count", 0)
                val duplicates = respJson.optInt("duplicate_count", 0)
                val sleepStatus = respJson.optString("sleep_status", "no_data_yet")

                // On successful transmission, update watermark and last seen measurement timestamp
                prefs.edit()
                    .putLong("last_sync_watermark_ms", now.toEpochMilli())
                    .putFloat("last_seen_measurement_ts", maxObservedMeasurementTs.toFloat())
                    .apply()

                SyncResult(
                    success = true,
                    recordsFoundCount = totalFound,
                    hrCount = hrFound,
                    stepsCount = stepsFound,
                    spo2Count = spo2Found,
                    sleepCount = sleepFound,
                    sleepDurationHours = latestSleepDurationHours,
                    sourcePackage = detectedSourcePackage,
                    serverAcceptedCount = inserted,
                    serverDuplicateCount = duplicates,
                    latestMeasurementTimestamp = maxObservedMeasurementTs,
                    isUpstreamStale = isUpstreamStale,
                    newRecordsObserved = newRecordsObserved,
                    message = "Successfully ingested $inserted new records ($duplicates duplicate/re-synced ignored).",
                    details = "Device: Fastrack Noir Charm\nSource: $detectedSourcePackage\nSleep Status: $sleepStatus\nSignals: ${respJson.optJSONObject("verified_signals")}"
                )
            }
        } catch (e: Exception) {
            SyncResult(
                success = false,
                recordsFoundCount = totalFound,
                hrCount = hrFound,
                stepsCount = stepsFound,
                spo2Count = spo2Found,
                sleepCount = sleepFound,
                sleepDurationHours = latestSleepDurationHours,
                sourcePackage = detectedSourcePackage,
                serverAcceptedCount = 0,
                serverDuplicateCount = 0,
                latestMeasurementTimestamp = maxObservedMeasurementTs,
                isUpstreamStale = isUpstreamStale,
                newRecordsObserved = newRecordsObserved,
                message = "Network connection failed to $cleanUrl: ${e.localizedMessage}",
                details = "Check that your MacBook is running the server (uvicorn main:app --host 0.0.0.0 --port 8000) and both devices are on the same network."
            )
        }
        return@withContext networkResult
    } finally {
        syncMutex.unlock()
    }
}
}
