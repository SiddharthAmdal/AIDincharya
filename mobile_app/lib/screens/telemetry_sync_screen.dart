// Flutter Telemetry Sync Screen — HealthKit & Health Connect Integration
import 'package:flutter/material.dart';
import '../api_service.dart';

class TelemetrySyncScreen extends StatefulWidget {
  final AiDincharyaApiService apiService;
  const TelemetrySyncScreen({Key? key, required this.apiService}) : super(key: key);

  @override
  _TelemetrySyncScreenState createState() => _TelemetrySyncScreenState();
}

class _TelemetrySyncScreenState extends State<TelemetrySyncScreen> {
  String _statusMsg = "Tap below to sync health telemetry.";
  bool _isSyncing = false;

  Future<void> _syncVendor(String provider) async {
    setState(() {
      _isSyncing = true;
      _statusMsg = "Syncing with $provider...";
    });

    final dummyPayload = provider == "apple_healthkit"
        ? {
            "HKQuantityTypeIdentifierHeartRateVariabilitySDNN": {"value": 38.0},
            "HKQuantityTypeIdentifierRestingHeartRate": {"value": 72.0},
            "HKCategoryTypeIdentifierSleepAnalysis": {"value": 6.0},
            "HKQuantityTypeIdentifierBodyTemperature": {"value": 36.8}
          }
        : {
            "hrv_rmssd_ms": 42.0,
            "resting_hr_bpm": 68.0,
            "sleep_duration_hours": 7.0,
            "body_temperature_celsius": 36.7
          };

    final resp = await widget.apiService.syncWearableData(provider, dummyPayload);
    setState(() {
      _isSyncing = false;
      _statusMsg = resp['status'] == 'success'
          ? "Successfully synced telemetry from $provider!"
          : "Sync failed. Please check connection.";
    });
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Wearable Health Sync'),
        backgroundColor: const Color(0xFF2C4A3E),
      ),
      body: Padding(
        padding: const EdgeInsets.all(16.0),
        child: Column(
          children: [
            Card(
              child: ListTile(
                leading: const Icon(Icons.apple, size: 36),
                title: const Text('Apple HealthKit'),
                subtitle: const Text('Sync HRV, Sleep & Temp'),
                trailing: ElevatedButton(
                  onPressed: _isSyncing ? null : () => _syncVendor('apple_healthkit'),
                  child: const Text('Sync'),
                ),
              ),
            ),
            const SizedBox(height: 12),
            Card(
              child: ListTile(
                leading: const Icon(Icons.android, size: 36, color: Colors.green),
                title: const Text('Google Health Connect'),
                subtitle: const Text('Sync RHR, HRV & Sleep Duration'),
                trailing: ElevatedButton(
                  onPressed: _isSyncing ? null : () => _syncVendor('google_healthconnect'),
                  child: const Text('Sync'),
                ),
              ),
            ),
            const SizedBox(height: 24),
            Text(_statusMsg, style: const TextStyle(fontSize: 16, fontWeight: FontWeight.w500)),
          ],
        ),
      ),
    );
  }
}
