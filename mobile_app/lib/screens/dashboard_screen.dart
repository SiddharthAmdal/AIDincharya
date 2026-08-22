// Flutter Dashboard Screen — Daily Routine Timeline & Adherence Ring
import 'package:flutter/material.dart';
import '../api_service.dart';

class DashboardScreen extends StatefulWidget {
  final AiDincharyaApiService apiService;
  const DashboardScreen({Key? key, required this.apiService}) : super(key: key);

  @override
  _DashboardScreenState createState() => _DashboardScreenState();
}

class _DashboardScreenState extends State<DashboardScreen> {
  Map<String, dynamic>? _scheduleData;
  bool _isLoading = true;

  @override
  void initState() {
    super.initState();
    _fetchSchedule();
  }

  Future<void> _fetchSchedule() async {
    setState(() => _isLoading = true);
    final data = await widget.apiService.getTodaySchedule();
    setState(() {
      _scheduleData = data;
      _isLoading = false;
    });
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Dinacharya AI Routine'),
        backgroundColor: const Color(0xFF2C4A3E),
      ),
      body: _isLoading
          ? const Center(child: CircularProgressIndicator())
          : _scheduleData == null || _scheduleData!['schedule'] == null
              ? Center(
                  child: ElevatedButton(
                    onPressed: () async {
                      await widget.apiService.generateSchedule({
                        'season': 'Winter',
                        'weather': 'Cold',
                        'temperature_c': 12.0,
                        'calendar_events': []
                      });
                      _fetchSchedule();
                    },
                    child: const Text('Generate Today\'s Schedule'),
                  ),
                )
              : ListView(
                  padding: const EdgeInsets.all(16.0),
                  children: [
                    _buildAdherenceCard(),
                    const SizedBox(height: 16),
                    _buildBlockHeader("🌅 Morning Block"),
                    ..._buildPracticeList(_scheduleData!['schedule']['morning_block'] ?? []),
                    _buildBlockHeader("☀️ Midday Block"),
                    ..._buildPracticeList(_scheduleData!['schedule']['midday_block'] ?? []),
                    _buildBlockHeader("🌙 Evening Block"),
                    ..._buildPracticeList(_scheduleData!['schedule']['evening_block'] ?? []),
                  ],
                ),
    );
  }

  Widget _buildAdherenceCard() {
    double score = (_scheduleData!['schedule']['adherence_score'] ?? 1.0) * 100;
    return Card(
      color: const Color(0xFFEAF2ED),
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
      child: Padding(
        padding: const EdgeInsets.all(16.0),
        child: Row(
          children: [
            CircularProgressIndicator(
              value: score / 100,
              backgroundColor: Colors.grey.shade300,
              color: const Color(0xFF2C4A3E),
            ),
            const SizedBox(width: 16),
            Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text('Adherence Score: ${score.toStringAsFixed(0)}%', style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 16)),
                Text('Complexity: ${_scheduleData!['schedule']['routine_complexity'] ?? 'Moderate'}', style: TextStyle(color: Colors.grey.shade700)),
              ],
            )
          ],
        ),
      ),
    );
  }

  Widget _buildBlockHeader(String title) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 8.0),
      child: Text(title, style: const TextStyle(fontSize: 18, fontWeight: FontWeight.bold, color: Color(0xFF2C4A3E))),
    );
  }

  List<Widget> _buildPracticeList(List practices) {
    return practices.map((p) => Card(
      margin: const EdgeInsets.only(bottom: 8.0),
      child: ListTile(
        title: Text(p['name'], style: const TextStyle(fontWeight: FontWeight.w600)),
        subtitle: Text('${p['time_slot']} • ${p['description']}'),
        trailing: Checkbox(
          value: false,
          onChanged: (val) async {
            await widget.apiService.logAdherence([p['name']], [p['name']]);
            _fetchSchedule();
          },
        ),
      ),
    )).toList();
  }
}
