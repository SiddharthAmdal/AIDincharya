// AiDincharya Mobile Client API Service (Flutter Dart Integration Layer)
// Connects native iOS & Android Flutter UI to the FastAPI backend service endpoints.

import 'dart:convert';
import 'package:http/http' as http;

class AiDincharyaApiService {
  final String baseUrl;
  String? authToken;

  AiDincharyaApiService({this.baseUrl = "http://localhost:8000"});

  void setAuthToken(String token) {
    authToken = token;
  }

  Map<String, String> _headers() {
    final headers = {"Content-Type": "application/json"};
    if (authToken != null) {
      headers["Authorization"] = "Bearer $authToken";
    }
    return headers;
  }

  // 1. Authentication Endpoints
  Future<Map<String, dynamic>> register(String username, String password) async {
    final res = await http.post(
      Uri.parse("$baseUrl/api/auth/register"),
      headers: _headers(),
      body: jsonEncode({"username": username, "password": password}),
    );
    return jsonDecode(res.body);
  }

  Future<Map<String, dynamic>> login(String username, String password) async {
    final res = await http.post(
      Uri.parse("$baseUrl/api/auth/login"),
      headers: _headers(),
      body: jsonEncode({"username": username, "password": password}),
    );
    final data = jsonDecode(res.body);
    if (data.containsKey("token")) {
      authToken = data["token"];
    }
    return data;
  }

  Future<bool> logout() async {
    final res = await http.post(
      Uri.parse("$baseUrl/api/auth/logout"),
      headers: _headers(),
    );
    authToken = null;
    return res.statusCode == 200;
  }

  // 2. Schedule Generation
  Future<Map<String, dynamic>> generateSchedule(Map<String, dynamic> contextData) async {
    final res = await http.post(
      Uri.parse("$baseUrl/api/schedule/generate"),
      headers: _headers(),
      body: jsonEncode({"user_id": "current", "context": contextData}),
    );
    return jsonDecode(res.body);
  }

  // 3. Today's Schedule
  Future<Map<String, dynamic>> getTodaySchedule() async {
    final res = await http.get(
      Uri.parse("$baseUrl/api/schedule/today"),
      headers: _headers(),
    );
    return jsonDecode(res.body);
  }

  // 4. Log Adherence
  Future<Map<String, dynamic>> logAdherence(List<String> completed, List<String> recommended) async {
    final res = await http.post(
      Uri.parse("$baseUrl/api/adherence/log"),
      headers: _headers(),
      body: jsonEncode({
        "user_id": "current",
        "completed_practices": completed,
        "recommended_practices": recommended
      }),
    );
    return jsonDecode(res.body);
  }

  // 5. Wearable Telemetry Sync
  Future<Map<String, dynamic>> syncWearableData(String provider, Map<String, dynamic> rawPayload) async {
    final res = await http.post(
      Uri.parse("$baseUrl/api/wearables/sync"),
      headers: _headers(),
      body: jsonEncode({"provider": provider, "raw_payload": rawPayload}),
    );
    return jsonDecode(res.body);
  }

  // 6. Vaidya AI Chat
  Future<Map<String, dynamic>> sendChatMessage(String message) async {
    final res = await http.post(
      Uri.parse("$baseUrl/api/chat"),
      headers: _headers(),
      body: jsonEncode({"message": message}),
    );
    return jsonDecode(res.body);
  }
}
