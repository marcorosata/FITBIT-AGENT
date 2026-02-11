/// AI Chat screen — free-form conversation with the LangGraph agent.
library;

import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../app_state.dart';
import '../theme.dart';

class ChatScreen extends StatefulWidget {
  const ChatScreen({super.key});

  @override
  State<ChatScreen> createState() => _ChatScreenState();
}

class _ChatScreenState extends State<ChatScreen> {
  final _controller = TextEditingController();
  final _scrollController = ScrollController();
  final List<_ChatMessage> _messages = [];
  bool _sending = false;

  @override
  void dispose() {
    _controller.dispose();
    _scrollController.dispose();
    super.dispose();
  }

  Future<void> _send() async {
    final text = _controller.text.trim();
    if (text.isEmpty || _sending) return;

    setState(() {
      _messages.add(_ChatMessage(text: text, isUser: true));
      _sending = true;
    });
    _controller.clear();
    _scrollToBottom();

    try {
      final state = context.read<AppState>();
      final response = await state.api.analyse(text);
      setState(() {
        _messages.add(_ChatMessage(text: response, isUser: false));
      });
    } catch (e) {
      setState(() {
        _messages.add(_ChatMessage(
            text: 'Error: $e', isUser: false, isError: true));
      });
    } finally {
      setState(() => _sending = false);
      _scrollToBottom();
    }
  }

  void _scrollToBottom() {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (_scrollController.hasClients) {
        _scrollController.animateTo(
          _scrollController.position.maxScrollExtent,
          duration: const Duration(milliseconds: 300),
          curve: Curves.easeOut,
        );
      }
    });
  }

  @override
  Widget build(BuildContext context) {
    return Column(
      children: [
        // Messages
        Expanded(
          child: _messages.isEmpty
              ? Center(
                  child: Column(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      Icon(Icons.psychology,
                          size: 64, color: AppTheme.accent.withOpacity(0.3)),
                      const SizedBox(height: 12),
                      const Text(
                        'Ask the AI agent anything about\nyour health data.',
                        textAlign: TextAlign.center,
                        style: TextStyle(
                            color: AppTheme.textSecondary, fontSize: 14),
                      ),
                      const SizedBox(height: 16),
                      Wrap(
                        spacing: 8,
                        children: [
                          _SuggestionChip('How is my heart rate today?', _onSuggestion),
                          _SuggestionChip('Analyse my sleep patterns', _onSuggestion),
                          _SuggestionChip('Any anomalies this week?', _onSuggestion),
                        ],
                      ),
                    ],
                  ),
                )
              : ListView.builder(
                  controller: _scrollController,
                  padding: const EdgeInsets.all(16),
                  itemCount: _messages.length,
                  itemBuilder: (context, i) => _MessageBubble(msg: _messages[i]),
                ),
        ),

        // Input bar
        Container(
          padding: const EdgeInsets.fromLTRB(16, 8, 8, 8),
          decoration: const BoxDecoration(
            color: AppTheme.surface,
            border: Border(top: BorderSide(color: AppTheme.border)),
          ),
          child: SafeArea(
            top: false,
            child: Row(
              children: [
                Expanded(
                  child: TextField(
                    controller: _controller,
                    textInputAction: TextInputAction.send,
                    onSubmitted: (_) => _send(),
                    decoration: const InputDecoration(
                      hintText: 'Ask the agent...',
                      border: InputBorder.none,
                      isDense: true,
                    ),
                  ),
                ),
                IconButton(
                  icon: _sending
                      ? const SizedBox(
                          width: 20,
                          height: 20,
                          child: CircularProgressIndicator(strokeWidth: 2))
                      : const Icon(Icons.send_rounded, color: AppTheme.accent),
                  onPressed: _sending ? null : _send,
                ),
              ],
            ),
          ),
        ),
      ],
    );
  }

  void _onSuggestion(String text) {
    _controller.text = text;
    _send();
  }
}

class _ChatMessage {
  final String text;
  final bool isUser;
  final bool isError;

  const _ChatMessage({
    required this.text,
    required this.isUser,
    this.isError = false,
  });
}

class _MessageBubble extends StatelessWidget {
  final _ChatMessage msg;
  const _MessageBubble({required this.msg});

  @override
  Widget build(BuildContext context) {
    return Align(
      alignment: msg.isUser ? Alignment.centerRight : Alignment.centerLeft,
      child: Container(
        margin: const EdgeInsets.only(bottom: 10),
        padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
        constraints:
            BoxConstraints(maxWidth: MediaQuery.of(context).size.width * 0.78),
        decoration: BoxDecoration(
          color: msg.isUser
              ? AppTheme.accent
              : msg.isError
                  ? AppTheme.danger.withOpacity(0.1)
                  : const Color(0xFFF0F0F5),
          borderRadius: BorderRadius.only(
            topLeft: const Radius.circular(16),
            topRight: const Radius.circular(16),
            bottomLeft: Radius.circular(msg.isUser ? 16 : 4),
            bottomRight: Radius.circular(msg.isUser ? 4 : 16),
          ),
        ),
        child: SelectableText(
          msg.text,
          style: TextStyle(
            color: msg.isUser
                ? Colors.white
                : msg.isError
                    ? AppTheme.danger
                    : AppTheme.textPrimary,
            fontSize: 14,
            height: 1.4,
          ),
        ),
      ),
    );
  }
}

class _SuggestionChip extends StatelessWidget {
  final String text;
  final void Function(String) onTap;
  const _SuggestionChip(this.text, this.onTap);

  @override
  Widget build(BuildContext context) {
    return ActionChip(
      label: Text(text, style: const TextStyle(fontSize: 12)),
      backgroundColor: AppTheme.accent.withOpacity(0.08),
      onPressed: () => onTap(text),
    );
  }
}
