/// HTTP + WebSocket client for the Wearable Agent FastAPI backend.
library;

import 'dart:async';
import 'dart:convert';
import 'package:http/http.dart' as http;
import 'package:http_parser/http_parser.dart';
import 'package:web_socket_channel/web_socket_channel.dart';
import 'models.dart';

class ApiClient {
  String baseUrl;
  String dataSource = 'dataset';  // 'dataset' or 'live'

  ApiClient({required this.baseUrl});

  // ── Helpers ──────────────────────────────────────────────

  Map<String, String> get _headers => {
        'Content-Type': 'application/json',
        'X-Data-Source': dataSource,
      };

  Uri _uri(String path, [Map<String, String>? query]) =>
      Uri.parse('$baseUrl$path').replace(queryParameters: query);

  Future<dynamic> _get(String path, [Map<String, String>? query]) async {
    final resp = await http.get(
      _uri(path, query),
      headers: {'X-Data-Source': dataSource},
    );
    if (resp.statusCode >= 400) {
      throw ApiException(resp.statusCode, resp.body);
    }
    return jsonDecode(resp.body);
  }

  Future<dynamic> _post(String path, Map<String, dynamic> body) async {
    final resp = await http.post(
      _uri(path),
      headers: _headers,
      body: jsonEncode(body),
    );
    if (resp.statusCode >= 400) {
      throw ApiException(resp.statusCode, resp.body);
    }
    return jsonDecode(resp.body);
  }

  Future<dynamic> _patch(String path, Map<String, dynamic> body) async {
    final resp = await http.patch(
      _uri(path),
      headers: _headers,
      body: jsonEncode(body),
    );
    if (resp.statusCode >= 400) {
      throw ApiException(resp.statusCode, resp.body);
    }
    return jsonDecode(resp.body);
  }

  Future<dynamic> _delete(String path) async {
    final resp = await http.delete(
      _uri(path),
      headers: {'X-Data-Source': dataSource},
    );
    if (resp.statusCode >= 400) {
      throw ApiException(resp.statusCode, resp.body);
    }
    return jsonDecode(resp.body);
  }

  Future<dynamic> _postEmpty(String path) async {
    final resp = await http.post(
      _uri(path),
      headers: _headers,
    );
    if (resp.statusCode >= 400) {
      throw ApiException(resp.statusCode, resp.body);
    }
    return jsonDecode(resp.body);
  }

  // ── Health & System ──────────────────────────────────────

  Future<Map<String, dynamic>> health() async {
    return await _get('/health') as Map<String, dynamic>;
  }

  Future<SystemInfo> getSystemInfo() async {
    final data = await _get('/system/info') as Map<String, dynamic>;
    return SystemInfo.fromJson(data);
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

  /// Ask the agent to perform a deep per-metric analysis.
  Future<String> analyseMetric(
    String participantId,
    String metric, {
    int hours = 24,
  }) async {
    final data = await _post(
        '/analyse/metric?'
        'participant_id=$participantId&metric=$metric&hours=$hours',
        {});
    return (data as Map<String, dynamic>)['analysis'] as String? ?? '';
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
    String messageTemplate =
        'Metric {metric_type} value {value} breached rule.',
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

  // ── Participants ─────────────────────────────────────────

  Future<List<Participant>> getParticipants({bool activeOnly = true}) async {
    final data = await _get('/participants', {
      'active_only': activeOnly.toString(),
    });
    return (data as List<dynamic>)
        .map((e) => Participant.fromJson(e as Map<String, dynamic>))
        .toList();
  }

  Future<Participant> getParticipant(String participantId) async {
    final data =
        await _get('/participants/$participantId') as Map<String, dynamic>;
    return Participant.fromJson(data);
  }

  Future<void> createParticipant(String participantId,
      {String displayName = '', String deviceType = 'fitbit'}) async {
    await _post('/participants', {
      'participant_id': participantId,
      'display_name': displayName,
      'device_type': deviceType,
    });
  }

  Future<void> updateParticipant(String participantId,
      {String? displayName, bool? active}) async {
    final body = <String, dynamic>{};
    if (displayName != null) body['display_name'] = displayName;
    if (active != null) body['active'] = active;
    await _patch('/participants/$participantId', body);
  }

  Future<void> deleteParticipant(String participantId) async {
    await _delete('/participants/$participantId');
  }

  // ── Fitbit Auth ──────────────────────────────────────────

  /// Returns the URL to redirect the user to for Fitbit OAuth.
  /// The backend handles the redirect & callback.
  String getFitbitAuthUrl(String participantId) {
    return '$baseUrl/auth/fitbit?participant_id=$participantId';
  }

  Future<FitbitTokenStatus> getFitbitTokenStatus(String participantId) async {
    final data = await _get('/auth/fitbit/status/$participantId')
        as Map<String, dynamic>;
    return FitbitTokenStatus.fromJson(data);
  }

  Future<void> refreshFitbitTokens(String participantId) async {
    await _postEmpty('/auth/fitbit/refresh/$participantId');
  }

  Future<void> revokeFitbitTokens(String participantId) async {
    await _delete('/auth/fitbit/$participantId');
  }

  // ── Sync ─────────────────────────────────────────────────

  Future<Map<String, dynamic>> syncParticipant(String participantId) async {
    return await _postEmpty('/sync/$participantId') as Map<String, dynamic>;
  }

  Future<Map<String, dynamic>> syncAll() async {
    return await _postEmpty('/sync') as Map<String, dynamic>;
  }

  Future<SyncStatus> getSyncStatus() async {
    final data = await _get('/sync/status') as Map<String, dynamic>;
    return SyncStatus.fromJson(data);
  }

  Future<List<dynamic>> getDevices(String participantId) async {
    final data =
        await _get('/sync/devices/$participantId') as Map<String, dynamic>;
    return data['devices'] as List<dynamic>? ?? [];
  }

  // ── Affect inference ─────────────────────────────────────

  Future<AffectState> runAffectInference(String participantId,
      {int windowSeconds = 300}) async {
    final data = await _post('/affect/$participantId', {
      'window_seconds': windowSeconds,
    });
    return AffectState.fromJson(data as Map<String, dynamic>);
  }

  Future<AffectState> getAffectState(String participantId) async {
    final data = await _get('/affect/$participantId') as Map<String, dynamic>;
    return AffectState.fromJson(data);
  }

  Future<Map<String, dynamic>> getAffectHistory(
    String participantId, {
    int hours = 24,
  }) async {
    return await _get('/affect/$participantId/history', {
      'hours': hours.toString(),
    }) as Map<String, dynamic>;
  }

  // ── EMA (Ecological Momentary Assessment) ────────────────

  Future<Map<String, dynamic>> submitEMA({
    required String participantId,
    int? arousal,
    int? valence,
    int? stress,
    String? emotionTag,
    String contextNote = '',
    String trigger = 'user_initiated',
  }) async {
    final body = <String, dynamic>{
      'participant_id': participantId,
      'context_note': contextNote,
      'trigger': trigger,
    };
    if (arousal != null) body['arousal'] = arousal;
    if (valence != null) body['valence'] = valence;
    if (stress != null) body['stress'] = stress;
    if (emotionTag != null) body['emotion_tag'] = emotionTag;

    return await _post('/ema', body) as Map<String, dynamic>;
  }

  Future<List<EMALabel>> getEMALabels(String participantId,
      {int limit = 50}) async {
    final data = await _get('/ema/$participantId', {
      'limit': limit.toString(),
    });
    return (data as List<dynamic>)
        .map((e) => EMALabel.fromJson(e as Map<String, dynamic>))
        .toList();
  }

  // ── Data ingestion ───────────────────────────────────────

  Future<Map<String, dynamic>> ingest({
    required String participantId,
    required String deviceType,
    required String metricType,
    required double value,
    String unit = '',
  }) async {
    return await _post('/ingest', {
      'participant_id': participantId,
      'device_type': deviceType,
      'metric_type': metricType,
      'value': value,
      'unit': unit,
    }) as Map<String, dynamic>;
  }

  // ── LifeSnaps streaming ───────────────────────────────────

  /// Start replaying ALL data for a participant from the LifeSnaps dataset.
  /// The backend streams data via the pipeline → WebSocket to connected clients.
  Future<Map<String, dynamic>> startLifeSnapsStream(
    String participantId, {
    double speed = 10.0,
    List<String>? metrics,
  }) async {
    final body = <String, dynamic>{
      'speed': speed,
    };
    if (metrics != null) body['metrics'] = metrics;
    return await _post('/lifesnaps/stream/$participantId', body)
        as Map<String, dynamic>;
  }

  /// List available LifeSnaps participant IDs.
  Future<List<String>> getLifeSnapsParticipants() async {
    final data = await _get('/lifesnaps/participants');
    return (data as List<dynamic>).map((e) => e.toString()).toList();
  }

  /// Sync (bulk-load) a participant's LifeSnaps data into the server DB.
  /// Returns once the sync is started; data loads in background.
  Future<Map<String, dynamic>> syncParticipantData(
    String participantId, {
    bool force = false,
  }) async {
    final path = force
        ? '/lifesnaps/sync/$participantId?force=true'
        : '/lifesnaps/sync/$participantId';
    return await _postEmpty(path) as Map<String, dynamic>;
  }

  /// Check whether a participant's data has been synced.
  Future<Map<String, dynamic>> getSyncParticipantStatus(
      String participantId) async {
    return await _get('/lifesnaps/sync/$participantId/status')
        as Map<String, dynamic>;
  }

  // ── Live Fitbit streaming ─────────────────────────────────

  /// Start streaming live Fitbit data for a participant.
  /// The backend fetches from the Fitbit API and pushes through the pipeline.
  Future<Map<String, dynamic>> startLiveFitbitStream(
    String participantId, {
    List<String>? metrics,
    bool continuous = false,
  }) async {
    final body = <String, dynamic>{
      'continuous': continuous,
    };
    if (metrics != null) body['metrics'] = metrics;
    return await _post('/sync/stream/$participantId', body)
        as Map<String, dynamic>;
  }

  // ── Voice chat ────────────────────────────────────────────

  /// Send a voice recording to the backend for transcription + agent analysis.
  /// Returns a map with 'transcript' and 'response' keys.
  Future<Map<String, String>> voiceChat(
    String filePath, {
    String participantId = '',
  }) async {
    final uri = _uri('/media/voice-chat');
    final request = http.MultipartRequest('POST', uri);
    request.fields['participant_id'] = participantId;

    final ext = filePath.split('.').last.toLowerCase();
    final mimeType = switch (ext) {
      'wav' => MediaType('audio', 'wav'),
      'mp3' => MediaType('audio', 'mpeg'),
      'm4a' => MediaType('audio', 'mp4'),
      'aac' => MediaType('audio', 'aac'),
      'ogg' => MediaType('audio', 'ogg'),
      _ => MediaType('audio', 'webm'),
    };

    request.files.add(await http.MultipartFile.fromPath(
      'file',
      filePath,
      contentType: mimeType,
    ));

    final streamed = await request.send();
    final body = await streamed.stream.bytesToString();
    if (streamed.statusCode >= 400) {
      throw ApiException(streamed.statusCode, body);
    }
    final data = jsonDecode(body) as Map<String, dynamic>;
    return {
      'transcript': (data['transcript'] as String?) ?? '',
      'response': (data['response'] as String?) ?? '',
    };
  }

  // ── Media upload ─────────────────────────────────────────

  /// Upload an audio or video file linked to a participant.
  Future<Map<String, dynamic>> uploadMedia(
    String filePath, {
    required String participantId,
    String label = '',
    String notes = '',
  }) async {
    final uri = _uri('/media/upload');
    final request = http.MultipartRequest('POST', uri);
    request.fields['participant_id'] = participantId;
    request.fields['label'] = label;
    request.fields['notes'] = notes;
    request.files.add(await http.MultipartFile.fromPath('file', filePath));

    final streamed = await request.send();
    final body = await streamed.stream.bytesToString();
    if (streamed.statusCode >= 400) {
      throw ApiException(streamed.statusCode, body);
    }
    return jsonDecode(body) as Map<String, dynamic>;
  }

  // ── WebSocket ────────────────────────────────────────────

  WebSocketChannel connectStream({String channel = 'all'}) {
    final wsUrl = baseUrl.replaceFirst('http', 'ws');
    return WebSocketChannel.connect(
        Uri.parse('$wsUrl/ws/stream?channel=$channel'));
  }
}

class ApiException implements Exception {
  final int statusCode;
  final String body;
  const ApiException(this.statusCode, this.body);

  @override
  String toString() => 'ApiException($statusCode): $body';
}
