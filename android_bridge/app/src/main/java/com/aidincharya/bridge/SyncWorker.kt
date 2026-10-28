package com.aidincharya.bridge

import android.content.Context
import android.util.Log
import androidx.work.CoroutineWorker
import androidx.work.WorkerParameters

class SyncWorker(
    appContext: Context,
    workerParams: WorkerParameters
) : CoroutineWorker(appContext, workerParams) {

    override suspend fun doWork(): Result {
        val prefs = applicationContext.getSharedPreferences("aidincharya_prefs", Context.MODE_PRIVATE)
        val serverUrl = prefs.getString("server_url", "http://192.168.68.105:8000") ?: "http://192.168.68.105:8000"
        val token = prefs.getString("auth_token", "") ?: ""

        if (token.isEmpty()) {
            Log.w("SyncWorker", "No auth token found in SharedPreferences, skipping background sync")
            return Result.success()
        }

        val bridge = HealthConnectBridge(applicationContext)
        if (!bridge.isHealthConnectAvailable() || !bridge.hasAllPermissions()) {
            Log.w("SyncWorker", "Health Connect not ready or permissions missing, skipping background sync")
            return Result.success()
        }

        return try {
            val result = bridge.syncWearableData(serverUrl, token)
            Log.i("SyncWorker", "Background sync completed: ${result.message}")
            if (result.success) {
                Result.success()
            } else {
                if (result.message.contains("HTTP 401") || result.message.contains("HTTP 403")) {
                    Log.w("SyncWorker", "Auth token revoked or expired (${result.message}). Clearing token to prevent repeated failed background syncs.")
                    prefs.edit().remove("auth_token").apply()
                    Result.failure()
                } else {
                    Result.retry()
                }
            }
        } catch (e: Exception) {
            Log.e("SyncWorker", "Background sync failed: ${e.message}", e)
            Result.retry()
        }
    }
}
