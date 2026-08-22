// AiDincharya Mobile Client Application Entry Point (Flutter)
import 'package:flutter/material.dart';
import 'api_service.dart';
import 'screens/dashboard_screen.dart';
import 'screens/vaidya_chat_screen.dart';
import 'screens/telemetry_sync_screen.dart';

void main() {
  runApp(const AiDincharyaApp());
}

class AiDincharyaApp extends StatelessWidget {
  const AiDincharyaApp({Key? key}) : super(key: key);

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'AiDincharya Mobile',
      theme: ThemeData(
        primarySwatch: Colors.green,
        scaffoldBackgroundColor: const Color(0xFFF7FAF8),
      ),
      home: const MainNavigationShell(),
    );
  }
}

class MainNavigationShell extends StatefulWidget {
  const MainNavigationShell({Key? key}) : super(key: key);

  @override
  _MainNavigationShellState createState() => _MainNavigationShellState();
}

class _MainNavigationShellState extends State<MainNavigationShell> {
  int _currentIndex = 0;
  final AiDincharyaApiService _apiService = AiDincharyaApiService();

  @override
  Widget build(BuildContext context) {
    final screens = [
      DashboardScreen(apiService: _apiService),
      VaidyaChatScreen(apiService: _apiService),
      TelemetrySyncScreen(apiService: _apiService),
    ];

    return Scaffold(
      body: screens[_currentIndex],
      bottomNavigationBar: BottomNavigationBar(
        currentIndex: _currentIndex,
        selectedItemColor: const Color(0xFF2C4A3E),
        onTap: (idx) => setState(() => _currentIndex = idx),
        items: const [
          BottomNavigationBarItem(icon: Icon(Icons.schedule), label: 'Routine'),
          BottomNavigationBarItem(icon: Icon(Icons.chat_bubble), label: 'Vaidya AI'),
          BottomNavigationBarItem(icon: Icon(Icons.watch), label: 'Wearable Sync'),
        ],
      ),
    );
  }
}
