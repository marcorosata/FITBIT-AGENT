/// HTTP + WebSocket client for the Wearable Agent FastAPI backend.
library;

import 'dart:async';
import 'dart:convert';
import 'package:http/http.dart' as http;
import 'package:web_socket_channel/web_socket_channel.dart';
import 'models.dart';

class ApiClient {
  String baseUrl;

  ApiClient({required this.baseUrl});

  // ── Helpers ──────────────────────────────────────────────

  Uri _uri(String path, [Map<String, String>? query]) =>
      Uri.parse('$baseUrl$path').replace(queryParameters: query);

  Future<dynamic> _get(String path, [Map<String, String>? query]) async {
    final resp = await http.get(_uri(path, query));
    if (resp.statusCode >= 400) {
      throw ApiException(resp.statusCode, resp.body);
    }
    return jsonDecode(resp.body);
  }

  Future<dynamic> _post(String path, Map<String, dynamic> body) async {
    final resp = await http.post(
      _uri(path),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode(body),
    );
    if (resp.statusCode >= 400) {
      throw ApiException(resp.statusCode, resp.body);
    }
    return jsonDecode(resp.body);
  }

  Future<dynamic> _delete(String path) async {
    final resp = await http.delete(_uri(path));
    if (resp.statusCode >= 400) {
      throw ApiException(resp.statusCode, resp.body);
    }
    return jsonDecode(resp.body);
  }

  // ── Health ───────────────────────────────────────────────

  Future<Map<String, dynamic>> health() async {
    return await _get('/health') as Map<String, dynamic>;
  }

  // ── Stats ────────────────────────────────────────────────

  Future<HealthStats> getStats() async {
    final data = await _get('/api/stats') as Map<String, dynamic>;
    return HealthStats.fromJson(data);
  }

  // ── Readings ─────────────────────────────────────────────

  Future<List<SensorReading>> getReadings(
    String participantId,
    String metric, {
    int limit = 50,
  }) async {
    final data = await _get('/readings/$participantId', {
      'metric': metric,
      'limit': limit.toString(),
    });
    return (data as List<dynamic>)
        .map((e) => SensorReading.fromJson(e as Map<String, dynamic>))
        .toList();
  }

  // ── Alerts ───────────────────────────────────────────────

  Future<List<Alert>> getAlerts(String participantId, {int limit = 50}) async {
    final data = await _get('/alerts/$participantId', {
      'limit': limit.toString(),
    });
    return (data as List<dynamic>)
        .map((e) => Alert.fromJson(e as Map<String, dynamic>))
        .toList();
  }

  // ── Agent analysis ───────────────────────────────────────

  Future<String> analyse(String query) async {
    final data = await _post('/analyse', {'query': query});
    return (data as Map<String, dynamic>)['response'] as String? ?? '';
  }

  // ── Evaluate participant ─────────────────────────────────

  Future<String> evaluate(
    String participantId, {
    String metric = 'heart_rate',
    int hours = 24,
  }) async {
    final data = await _get('/evaluate/$participantId', {
      'metric': metric,
      'hours': hours.toString(),
    });
    return (data as Map<String, dynamic>)['evaluation'] as String? ?? '';
  }

  // ── Rules ────────────────────────────────────────────────

  Future<List<MonitoringRule>> getRules() async {
    final data = await _get('/rules');
    return (data as List<dynamic>)
        .map((e) => MonitoringRule.fromJson(e as Map<String, dynamic>))
        .toList();
  }

  Future<String> addRule({
    required String metricType,
    required String condition,
    String severity = 'warning',
    String messageTemplate = 'Metric {metric_type} value {value} breached rule.',
  }) async {
    final data = await _post('/rules', {
      'metric_type': metricType,
      'condition': condition,
      'severity': severity,
      'message_template': messageTemplate,
    });
    return (data as Map<String, dynamic>)['rule_id'] as String? ?? '';
  }

  Future<void> deleteRule(String ruleId) async {
    await _delete('/rules/$ruleId');
  }

  // ── WebSocket ────────────────────────────────────────────

  WebSocketChannel connectStream() {
    final wsUrl = baseUrl.replaceFirst('http', 'ws');
    return WebSocketChannel.connect(Uri.parse('$wsUrl/ws/stream'));
  }
}

class ApiException implements Exception {
  final int statusCode;
  final String body;
  const ApiException(this.statusCode, this.body);

  @override
  String toString() => 'ApiException($statusCode): $body';
}
