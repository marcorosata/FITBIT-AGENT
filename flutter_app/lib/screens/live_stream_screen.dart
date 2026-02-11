/// Live Stream screen — real-time readings via WebSocket.
library;

import 'dart:async';
import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'package:web_socket_channel/web_socket_channel.dart';
import '../app_state.dart';
import '../config.dart';
import '../theme.dart';

class LiveStreamScreen extends StatefulWidget {
  const LiveStreamScreen({super.key});

  @override
  State<LiveStreamScreen> createState() => _LiveStreamScreenState();
}

class _LiveStreamScreenState extends State<LiveStreamScreen> {
  WebSocketChannel? _channel;
  final List<_StreamEvent> _events = [];
  bool _connected = false;
  String? _error;

  @override
  void dispose() {
    _disconnect();
    super.dispose();
  }

  void _connect() {
    final state = context.read<AppState>();
    final baseUrl = state.baseUrl.isNotEmpty
        ? state.baseUrl
        : AppConfig.defaultBaseUrl;

    // http → ws, https → wss
    final wsUrl = baseUrl
        .replaceFirst('http://', 'ws://')
        .replaceFirst('https://', 'wss://');

    try {
      _channel = WebSocketChannel.connect(Uri.parse('$wsUrl/ws/stream'));
      setState(() {
        _connected = true;
        _error = null;
      });

      _channel!.stream.listen(
        (data) {
          try {
            final json = jsonDecode(data as String) as Map<String, dynamic>;
            setState(() {
              _events.insert(0, _StreamEvent.fromJson(json));
              if (_events.length > 200) _events.removeLast();
            });
          } catch (e) {
            setState(() {
              _events.insert(
                0,
                _StreamEvent(
                    type: 'raw',
                    metric: '',
                    value: 0,
                    unit: '',
                    participant: '',
                    timestamp: DateTime.now().toIso8601String(),
                    raw: data.toString()),
              );
            });
          }
        },
        onError: (e) => setState(() {
          _connected = false;
          _error = 'WebSocket error: $e';
        }),
        onDone: () => setState(() => _connected = false),
      );
    } catch (e) {
      setState(() {
        _connected = false;
        _error = 'Failed to connect: $e';
      });
    }
  }

  void _disconnect() {
    _channel?.sink.close();
    _channel = null;
    if (mounted) setState(() => _connected = false);
  }

  @override
  Widget build(BuildContext context) {
    return Column(
      children: [
        // ── Connection bar ──
        Container(
          padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 10),
          decoration: BoxDecoration(
            color: _connected
                ? AppTheme.success.withOpacity(0.08)
                : AppTheme.surface,
            border: const Border(bottom: BorderSide(color: AppTheme.border)),
          ),
          child: Row(
            children: [
              Icon(
                _connected ? Icons.sensors : Icons.sensors_off,
                color: _connected ? AppTheme.success : AppTheme.textSecondary,
                size: 20,
              ),
              const SizedBox(width: 8),
              Text(
                _connected ? 'Connected' : 'Disconnected',
                style: TextStyle(
                  fontWeight: FontWeight.w600,
                  color: _connected ? AppTheme.success : AppTheme.textSecondary,
                ),
              ),
              const Spacer(),
              Text('${_events.length} events',
                  style:
                      const TextStyle(fontSize: 12, color: AppTheme.textSecondary)),
              const SizedBox(width: 12),
              FilledButton.tonal(
                onPressed: _connected ? _disconnect : _connect,
                child: Text(_connected ? 'Stop' : 'Start'),
              ),
            ],
          ),
        ),

        if (_error != null)
          Container(
            width: double.infinity,
            padding: const EdgeInsets.all(12),
            color: AppTheme.danger.withOpacity(0.08),
            child: Text(_error!,
                style: const TextStyle(color: AppTheme.danger, fontSize: 12)),
          ),

        // ── Event list ──
        Expanded(
          child: _events.isEmpty
              ? Center(
                  child: Column(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      Icon(Icons.stream,
                          size: 64,
                          color: AppTheme.accent.withOpacity(0.3)),
                      const SizedBox(height: 12),
                      Text(
                        _connected
                            ? 'Waiting for data…'
                            : 'Tap Start to open the live stream.',
                        style: const TextStyle(color: AppTheme.textSecondary),
                      ),
                    ],
                  ),
                )
              : ListView.builder(
                  itemCount: _events.length,
                  itemBuilder: (context, i) => _EventTile(event: _events[i]),
                ),
        ),
      ],
    );
  }
}

class _StreamEvent {
  final String type;
  final String metric;
  final double value;
  final String unit;
  final String participant;
  final String timestamp;
  final String? raw;

  const _StreamEvent({
    required this.type,
    required this.metric,
    required this.value,
    required this.unit,
    required this.participant,
    required this.timestamp,
    this.raw,
  });

  factory _StreamEvent.fromJson(Map<String, dynamic> json) {
    return _StreamEvent(
      type: (json['type'] ?? json['metric_type'] ?? 'unknown') as String,
      metric: (json['metric_type'] ?? json['type'] ?? '') as String,
      value: (json['value'] as num?)?.toDouble() ?? 0,
      unit: (json['unit'] ?? '') as String,
      participant: (json['participant_id'] ?? '') as String,
      timestamp: (json['timestamp'] ?? DateTime.now().toIso8601String()) as String,
    );
  }
}

class _EventTile extends StatelessWidget {
  final _StreamEvent event;
  const _EventTile({required this.event});

  @override
  Widget build(BuildContext context) {
    final color = AppTheme.metricColor(event.metric);

    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
      decoration: const BoxDecoration(
        border: Border(bottom: BorderSide(color: AppTheme.border, width: 0.5)),
      ),
      child: Row(
        children: [
          Icon(AppTheme.metricIcon(event.metric), color: color, size: 18),
          const SizedBox(width: 10),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  event.raw ?? '${event.metric.replaceAll('_', ' ')} — ${event.participant}',
                  style: const TextStyle(fontSize: 13, fontWeight: FontWeight.w500),
                ),
                Text(_formatTs(event.timestamp),
                    style: const TextStyle(
                        fontSize: 11, color: AppTheme.textSecondary)),
              ],
            ),
          ),
          Text(
            '${event.value} ${event.unit}',
            style: TextStyle(
                fontWeight: FontWeight.w700, color: color, fontSize: 15),
          ),
        ],
      ),
    );
  }

  String _formatTs(String ts) {
    try {
      final dt = DateTime.parse(ts);
      return '${dt.hour.toString().padLeft(2, '0')}:${dt.minute.toString().padLeft(2, '0')}:${dt.second.toString().padLeft(2, '0')}';
    } catch (_) {
      return ts;
    }
  }
}
