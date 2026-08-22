// Flutter Vaidya AI Chat Screen — Interactive Chat & Recalibration
import 'package:flutter/material.dart';
import '../api_service.dart';

class VaidyaChatScreen extends StatefulWidget {
  final AiDincharyaApiService apiService;
  const VaidyaChatScreen({Key? key, required this.apiService}) : super(key: key);

  @override
  _VaidyaChatScreenState createState() => _VaidyaChatScreenState();
}

class _VaidyaChatScreenState extends State<VaidyaChatScreen> {
  final TextEditingController _messageController = TextEditingController();
  final List<Map<String, String>> _messages = [];
  bool _isSending = false;

  Future<void> _sendMessage() async {
    final text = _messageController.text.trim();
    if (text.isEmpty) return;

    setState(() {
      _messages.add({'sender': 'user', 'text': text});
      _messageController.clear();
      _isSending = true;
    });

    final resp = await widget.apiService.sendChatMessage(text);
    setState(() {
      _messages.add({'sender': 'vaidya', 'text': resp['response'] ?? 'Namaste! How can I assist your routine today?'});
      _isSending = false;
    });
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Vaidya AI Consultant'),
        backgroundColor: const Color(0xFF2C4A3E),
      ),
      body: Column(
        children: [
          Expanded(
            child: ListView.builder(
              padding: const EdgeInsets.all(16.0),
              itemCount: _messages.length,
              itemBuilder: (context, idx) {
                final m = _messages[idx];
                final isUser = m['sender'] == 'user';
                return Align(
                  alignment: isUser ? Alignment.centerRight : Alignment.centerLeft,
                  child: Container(
                    margin: const EdgeInsets.only(bottom: 8.0),
                    padding: const EdgeInsets.all(12.0),
                    decoration: BoxDecoration(
                      color: isUser ? const Color(0xFF2C4A3E) : Colors.grey.shade200,
                      borderRadius: BorderRadius.circular(12),
                    ),
                    child: Text(
                      m['text']!,
                      style: TextStyle(color: isUser ? Colors.white : Colors.black87),
                    ),
                  ),
                );
              },
            ),
          ),
          if (_isSending) const LinearProgressIndicator(),
          Padding(
            padding: const EdgeInsets.all(8.0),
            child: Row(
              children: [
                Expanded(
                  child: TextField(
                    controller: _messageController,
                    decoration: const InputDecoration(
                      hintText: 'Ask Vaidya AI (e.g. "I have fever today")...',
                      border: OutlineInputBorder(),
                    ),
                  ),
                ),
                IconButton(
                  icon: const Icon(Icons.send, color: Color(0xFF2C4A3E)),
                  onPressed: _sendMessage,
                )
              ],
            ),
          )
        ],
      ),
    );
  }
}
