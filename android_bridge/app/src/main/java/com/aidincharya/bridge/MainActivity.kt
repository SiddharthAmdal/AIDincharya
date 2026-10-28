package com.aidincharya.bridge

import android.content.Context
import android.os.Bundle
import android.view.View
import android.widget.Button
import android.widget.TextView
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity
import androidx.health.connect.client.PermissionController
import androidx.lifecycle.lifecycleScope
import androidx.work.Constraints
import androidx.work.ExistingPeriodicWorkPolicy
import androidx.work.NetworkType
import androidx.work.PeriodicWorkRequestBuilder
import androidx.work.WorkManager
import com.google.android.material.switchmaterial.SwitchMaterial
import com.google.android.material.textfield.TextInputEditText
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import org.json.JSONObject
import java.util.concurrent.TimeUnit

class MainActivity : AppCompatActivity() {

    private lateinit var bridge: HealthConnectBridge

    private lateinit var etServerUrl: TextInputEditText
    private lateinit var etUsername: TextInputEditText
    private lateinit var etPassword: TextInputEditText
    private lateinit var etToken: TextInputEditText
    private lateinit var tvHealthConnectStatus: TextView
    private lateinit var tvPermissionsStatus: TextView
    private lateinit var btnRequestPermissions: Button
    private lateinit var btnSyncNow: Button
    private lateinit var switchBackgroundSync: SwitchMaterial
    private lateinit var tvSyncLog: TextView

    private var foregroundPollingJob: kotlinx.coroutines.Job? = null
    private var lastSyncAttemptTimestamp: Long = 0L

    // Modern Health Connect permission launcher
    private val requestPermissionLauncher = registerForActivityResult(
        PermissionController.createRequestPermissionResultContract()
    ) { _: Set<String> ->
        lifecycleScope.launch {
            checkPermissionsState()
            startForegroundPollingIfEligible()
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)

        bridge = HealthConnectBridge(this)

        etServerUrl = findViewById(R.id.etServerUrl)
        etUsername = findViewById(R.id.etUsername)
        etPassword = findViewById(R.id.etPassword)
        etToken = findViewById(R.id.etToken)
        tvHealthConnectStatus = findViewById(R.id.tvHealthConnectStatus)
        tvPermissionsStatus = findViewById(R.id.tvPermissionsStatus)
        btnRequestPermissions = findViewById(R.id.btnRequestPermissions)
        btnSyncNow = findViewById(R.id.btnSyncNow)
        switchBackgroundSync = findViewById(R.id.switchBackgroundSync)
        tvSyncLog = findViewById(R.id.tvSyncLog)

        // Load saved preferences if any
        val prefs = getSharedPreferences("aidincharya_prefs", Context.MODE_PRIVATE)
        val savedUrl = prefs.getString("server_url", "http://192.168.68.105:8000")
        val savedToken = prefs.getString("auth_token", "")
        val autoSync = prefs.getBoolean("auto_sync_enabled", true)

        if (!savedUrl.isNullOrEmpty()) etServerUrl.setText(savedUrl)
        if (!savedToken.isNullOrEmpty()) etToken.setText(savedToken)
        switchBackgroundSync.isChecked = autoSync

        btnRequestPermissions.setOnClickListener {
            requestHealthConnectPermissions()
        }

        btnSyncNow.setOnClickListener {
            startSyncFlow(isAutomated = false)
        }

        switchBackgroundSync.setOnCheckedChangeListener { _, isChecked ->
            prefs.edit().putBoolean("auto_sync_enabled", isChecked).apply()
            schedulePeriodicSync(isChecked)
            val stateText = if (isChecked) "enabled (15m WorkManager background fallback)" else "disabled"
            Toast.makeText(this, "Background sync $stateText", Toast.LENGTH_SHORT).show()
        }

        // Schedule background WorkManager fallback if enabled
        if (autoSync && !savedToken.isNullOrEmpty()) {
            schedulePeriodicSync(true)
        }
    }

    override fun onResume() {
        super.onResume()
        lifecycleScope.launch {
            checkHealthConnectAvailability()
            checkPermissionsState()
            startForegroundPollingIfEligible()
        }
    }

    override fun onPause() {
        super.onPause()
        // Stop foreground 1-minute polling loop when activity leaves the foreground
        foregroundPollingJob?.cancel()
        foregroundPollingJob = null
    }

    private suspend fun startForegroundPollingIfEligible() {
        if (foregroundPollingJob?.isActive == true) return
        if (!bridge.hasAllPermissions()) return

        val token = etToken.text?.toString()?.trim() ?: ""
        if (token.isEmpty()) return

        foregroundPollingJob = lifecycleScope.launch {
            while (isActive) {
                val now = System.currentTimeMillis()
                if (now - lastSyncAttemptTimestamp >= 10_000L) { // Debounce 10 seconds
                    startSyncFlow(isAutomated = true)
                }
                // Intended 60-second polling cadence while app is in foreground
                kotlinx.coroutines.delay(60_000L)
            }
        }
    }

    private suspend fun checkHealthConnectAvailability() {
        val available = bridge.isHealthConnectAvailable()
        if (available) {
            tvHealthConnectStatus.text = "✓ Health Connect is Available & Ready"
            tvHealthConnectStatus.setTextColor(getColor(android.R.color.holo_green_dark))
            btnRequestPermissions.isEnabled = true
        } else {
            tvHealthConnectStatus.text = "✗ Health Connect is NOT available on this device"
            tvHealthConnectStatus.setTextColor(getColor(android.R.color.holo_red_dark))
            btnRequestPermissions.isEnabled = false
        }
    }

    private suspend fun checkPermissionsState() {
        val hasAll = bridge.hasAllPermissions()
        val granted = bridge.getGrantedPermissions()
        if (hasAll) {
            tvPermissionsStatus.text = "✓ All Permissions Granted (Heart Rate, Steps, SpO2, Sleep)"
            tvPermissionsStatus.setTextColor(getColor(android.R.color.holo_green_dark))
            btnRequestPermissions.visibility = View.GONE
        } else {
            val count = granted.size
            tvPermissionsStatus.text = "⚠ $count / ${HealthConnectBridge.REQUIRED_PERMISSIONS.size} permissions granted."
            tvPermissionsStatus.setTextColor(getColor(android.R.color.holo_orange_dark))
            btnRequestPermissions.visibility = View.VISIBLE
        }
    }

    private fun requestHealthConnectPermissions() {
        requestPermissionLauncher.launch(HealthConnectBridge.REQUIRED_PERMISSIONS)
    }

    /**
     * WorkManager constraint: Periodic work has a platform-enforced minimum repeat interval of 15 minutes.
     * It cannot guarantee execution every minute. WorkManager is strictly retained here as a periodic
     * background fallback, while 1-minute polling is executed in the foreground via lifecycle coroutines.
     */
    private fun schedulePeriodicSync(enabled: Boolean) {
        val workManager = WorkManager.getInstance(this)
        if (enabled) {
            val constraints = Constraints.Builder()
                .setRequiredNetworkType(NetworkType.CONNECTED)
                .build()
            val syncRequest = PeriodicWorkRequestBuilder<SyncWorker>(15, TimeUnit.MINUTES)
                .setConstraints(constraints)
                .build()
            workManager.enqueueUniquePeriodicWork(
                "WearablePeriodicSync",
                ExistingPeriodicWorkPolicy.UPDATE,
                syncRequest
            )
        } else {
            workManager.cancelUniqueWork("WearablePeriodicSync")
        }
    }

    private fun startSyncFlow(isAutomated: Boolean = false) {
        val serverUrl = etServerUrl.text?.toString()?.trim() ?: "http://192.168.68.105:8000"
        val existingToken = etToken.text?.toString()?.trim() ?: ""
        val username = etUsername.text?.toString()?.trim() ?: ""
        val password = etPassword.text?.toString()?.trim() ?: ""

        val modeLabel = if (isAutomated) "[1-Min Auto Polling]" else "[Manual Sync]"
        if (!isAutomated) {
            tvSyncLog.text = "$modeLabel Initiating synchronization...\nChecking connection to: $serverUrl\n"
            btnSyncNow.isEnabled = false
        }

        lastSyncAttemptTimestamp = System.currentTimeMillis()

        lifecycleScope.launch {
            try {
                var token = existingToken

                // If username and password are provided and token is missing or manual sync, authenticate
                if (username.isNotEmpty() && password.isNotEmpty() && (!isAutomated || token.isEmpty())) {
                    if (!isAutomated) tvSyncLog.append("Authenticating user '$username'...\n")
                    token = authenticateUser(serverUrl, username, password)
                    etToken.setText(token)
                    if (!isAutomated) tvSyncLog.append("✓ Authentication successful. Bearer session established for '$username'.\n")
                }

                if (token.isEmpty()) {
                    if (!isAutomated) tvSyncLog.append("✗ Error: No authentication token or credentials provided.\n")
                    btnSyncNow.isEnabled = true
                    return@launch
                }

                // Save configuration for background WorkManager and next foreground session
                val prefs = getSharedPreferences("aidincharya_prefs", Context.MODE_PRIVATE)
                prefs.edit()
                    .putString("server_url", serverUrl)
                    .putString("auth_token", token)
                    .apply()

                if (switchBackgroundSync.isChecked) {
                    schedulePeriodicSync(true)
                }

                val syncStart = java.text.SimpleDateFormat("HH:mm:ss", java.util.Locale.getDefault()).format(java.util.Date())
                val result = bridge.syncWearableData(serverUrl, token)

                val logBuilder = StringBuilder()
                logBuilder.append("──────────────────────────────────\n")
                logBuilder.append("$modeLabel Sync at $syncStart:\n")

                if (result.success) {
                    logBuilder.append("Status: ✓ Last sync successful\n")
                    logBuilder.append("Health Connect records read: ${result.recordsFoundCount}\n")
                    logBuilder.append("  • Heart Rate: ${result.hrCount} samples\n")
                    logBuilder.append("  • Steps: ${result.stepsCount} records\n")
                    logBuilder.append("  • SpO2: ${result.spo2Count} records\n")
                    logBuilder.append("  • Sleep: ${result.sleepCount} sessions (${String.format(java.util.Locale.US, "%.1f", result.sleepDurationHours)}h)\n")
                    logBuilder.append("Backend Ingestion: ${result.serverAcceptedCount} inserted, ${result.serverDuplicateCount} duplicates skipped\n")

                    if (result.latestMeasurementTimestamp > 0.0) {
                        val measDate = java.util.Date((result.latestMeasurementTimestamp * 1000).toLong())
                        val measFormatted = java.text.SimpleDateFormat("yyyy-MM-dd HH:mm:ss", java.util.Locale.getDefault()).format(measDate)
                        val ageMins = ((System.currentTimeMillis() - measDate.time) / 60000).toInt()
                        logBuilder.append("Latest Watch Reading: $measFormatted ($ageMins mins ago)\n")
                    }

                    if (result.isUpstreamStale) {
                        logBuilder.append("\n⚠ UPSTREAM DATA STALE:\n")
                        logBuilder.append("Fastrack companion app has not synced recent biometrics to Health Connect.\n")
                        logBuilder.append("👉 ACTION REQUIRED: Please open Fastrack Smart World app on this phone to pull fresh records from your Noir Charm.\n")
                    } else if (result.recordsFoundCount == 0) {
                        logBuilder.append("Note: No new Health Connect records in bounded window.\n")
                    }

                    logBuilder.append("Message: ${result.message}\n")
                    if (!isAutomated) {
                        Toast.makeText(this@MainActivity, if (result.isUpstreamStale) "Sync OK (Fastrack data stale - open Fastrack app)" else "Sync Successful!", Toast.LENGTH_SHORT).show()
                    }
                } else {
                    logBuilder.append("Status: ✗ Sync failed\n")
                    logBuilder.append("Reason: ${result.message}\n")
                    logBuilder.append(result.details)
                    if (!isAutomated) {
                        Toast.makeText(this@MainActivity, "Sync Failed: ${result.message}", Toast.LENGTH_LONG).show()
                    }
                }

                tvSyncLog.text = logBuilder.toString()

            } catch (e: Exception) {
                tvSyncLog.append("──────────────────────────────────\n")
                tvSyncLog.append("✗ Unexpected Error: ${e.localizedMessage}\n")
            } finally {
                btnSyncNow.isEnabled = true
            }
        }
    }

    private suspend fun authenticateUser(serverUrl: String, u: String, p: String): String = withContext(Dispatchers.IO) {
        val client = OkHttpClient()
        val authUrl = serverUrl.trimEnd('/') + "/api/auth/login"
        val payload = JSONObject().apply {
            put("username", u)
            put("password", p)
        }
        val body = payload.toString().toRequestBody("application/json".toMediaType())
        val req = Request.Builder().url(authUrl).post(body).build()

        val resp = client.newCall(req).execute()
        val bodyStr = resp.body?.string() ?: ""

        if (resp.code == 400 || resp.code == 401) {
            // Attempt auto-register if user doesn't exist yet on local dev backend
            val regUrl = serverUrl.trimEnd('/') + "/api/auth/register"
            val regReq = Request.Builder().url(regUrl).post(body).build()
            val regResp = client.newCall(regReq).execute()
            val regBody = regResp.body?.string() ?: ""
            if (regResp.isSuccessful) {
                val regJson = JSONObject(regBody)
                return@withContext regJson.getString("token")
            }
        }

        if (!resp.isSuccessful) {
            throw IllegalStateException("Authentication failed (HTTP ${resp.code}): $bodyStr")
        }

        val json = JSONObject(bodyStr)
        json.getString("token")
    }
}
