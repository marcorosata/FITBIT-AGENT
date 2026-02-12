/// Central app state managed via Provider / ChangeNotifier.
library;

import 'package:flutter/foundation.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'api_client.dart';
import 'config.dart';
import 'models.dart';

class AppState extends ChangeNotifier {
  late ApiClient _api;
  String _participantId = '';
  bool _loading = false;
  String? _error;
  bool _useDataset = true;  // true = dataset (LifeSnaps), false = live Fitbit

  // Cached data
  HealthStats? stats;
  List<SensorReading> readings = [];
  List<Alert> alerts = [];
  List<MonitoringRule> rules = [];
  String _selectedMetric = 'hrv';

  // New: extended state for full backend connectivity
  List<Participant> participants = [];
  Participant? currentParticipant;
  AffectState? affectState;
  FitbitTokenStatus? fitbitStatus;
  SyncStatus? syncStatus;
  SystemInfo? systemInfo;
  List<EMALabel> emaLabels = [];
  bool _streaming = false;
  String? _streamError;

  AppState() {
    _api = ApiClient(baseUrl: AppConfig.baseUrl);
    _loadPrefs();
  }

  // ── Getters ──────────────────────────────────────────────

  String get baseUrl => AppConfig.baseUrl;
  String get participantId => _participantId;
  bool get loading => _loading;
  String? get error => _error;
  String get selectedMetric => _selectedMetric;
  ApiClient get api => _api;
  bool get hasParticipant => _participantId.isNotEmpty;
  bool get streaming => _streaming;
  String? get streamError => _streamError;
  bool get useDataset => _useDataset;
  String get dataSource => _useDataset ? 'dataset' : 'live';

  // ── Prefs ────────────────────────────────────────────────

  Future<void> _loadPrefs() async {
    final prefs = await SharedPreferences.getInstance();
    _participantId = prefs.getString(AppConfig.keyParticipantId) ?? '';
    _useDataset = prefs.getBool('data_source_is_dataset') ?? true;
    _api.dataSource = dataSource;  // Set data source on API client
    notifyListeners();
    if (_participantId.isNotEmpty) {
      await refreshAll();
    }
  }

  Future<void> setParticipantId(String id) async {
    _participantId = id.trim();
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(AppConfig.keyParticipantId, _participantId);
    notifyListeners();
    if (_participantId.isNotEmpty) {
      // Auto-register participant on backend if not yet known
      try {
        await _api.createParticipant(_participantId);
      } catch (_) {
        // 409 = already exists — perfectly fine
      }
      await refreshAll();
    }
  }

  void setMetric(String metric) {
    _selectedMetric = metric;
    notifyListeners();
    if (hasParticipant) fetchReadings();
  }

  Future<void> setDataSource(bool useDataset) async {
    _useDataset = useDataset;
    final prefs = await SharedPreferences.getInstance();
    await prefs.setBool('data_source_is_dataset', _useDataset);
    _api.dataSource = dataSource;  // Update API client
    notifyListeners();
    // Refresh data with new source
    if (hasParticipant) {
      await refreshAll();
    }
  }

  // ── Data fetching ────────────────────────────────────────

  Future<void> refreshAll() async {
    _loading = true;
    _error = null;
    notifyListeners();
    try {
      // Use individual try/catch so one failing endpoint doesn't block others
      final futures = <Future>[
        fetchStats(),
        fetchReadings(),
        fetchAlerts(),
        fetchRules(),
        fetchParticipants(),
        fetchFitbitStatus(),
        fetchSyncStatus(),
        fetchSystemInfo(),
        fetchAffectState(),
        fetchEMALabels(),
      ];
      await Future.wait(futures, eagerError: false);
      // Also fetch current participant details
      if (hasParticipant) {
        await fetchCurrentParticipant();
      }
    } catch (e) {
      _error = e.toString();
    }
    _loading = false;
    notifyListeners();
  }

  Future<void> fetchStats() async {
    try {
      stats = await _api.getStats();
    } catch (e) {
      _error = 'Stats: $e';
    }
    notifyListeners();
  }

  /// Metrics to try when the selected one returns no data.
  static const _fallbackMetrics = [
    'hrv',
    'resting_heart_rate',
    'stress',
    'skin_temperature',
    'breathing_rate',
    'sleep_efficiency',
    'heart_rate',
    'steps',
  ];

  Future<void> fetchReadings() async {
    if (!hasParticipant) return;
    try {
      readings = await _api.getReadings(_participantId, _selectedMetric);
      // Auto-fallback: if no readings for the current metric, try alternatives
      if (readings.isEmpty) {
        for (final alt in _fallbackMetrics) {
          if (alt == _selectedMetric) continue;
          final altReadings = await _api.getReadings(_participantId, alt);
          if (altReadings.isNotEmpty) {
            _selectedMetric = alt;
            readings = altReadings;
            break;
          }
        }
      }
    } catch (e) {
      _error = 'Readings: $e';
    }
    notifyListeners();
  }

  Future<void> fetchAlerts() async {
    if (!hasParticipant) return;
    try {
      alerts = await _api.getAlerts(_participantId);
    } catch (e) {
      _error = 'Alerts: $e';
    }
    notifyListeners();
  }

  Future<void> fetchRules() async {
    try {
      rules = await _api.getRules();
    } catch (e) {
      _error = 'Rules: $e';
    }
    notifyListeners();
  }

  // ── Participants ─────────────────────────────────────────

  Future<void> fetchParticipants() async {
    try {
      participants = await _api.getParticipants();
    } catch (e) {
      // Non-critical — ignore silently
    }
    notifyListeners();
  }

  Future<void> fetchCurrentParticipant() async {
    if (!hasParticipant) return;
    try {
      currentParticipant = await _api.getParticipant(_participantId);
    } catch (e) {
      currentParticipant = null;
    }
    notifyListeners();
  }

  Future<void> registerParticipant(String id, {String displayName = ''}) async {
    await _api.createParticipant(id, displayName: displayName);
    await fetchParticipants();
  }

  // ── Fitbit Auth ──────────────────────────────────────────

  Future<void> fetchFitbitStatus() async {
    if (!hasParticipant) return;
    try {
      fitbitStatus = await _api.getFitbitTokenStatus(_participantId);
    } catch (e) {
      fitbitStatus = null;
    }
    notifyListeners();
  }

  Future<void> refreshFitbitTokens() async {
    if (!hasParticipant) return;
    await _api.refreshFitbitTokens(_participantId);
    await fetchFitbitStatus();
  }

  Future<void> revokeFitbitTokens() async {
    if (!hasParticipant) return;
    await _api.revokeFitbitTokens(_participantId);
    await fetchFitbitStatus();
  }

  /// URL to open in browser for Fitbit OAuth (backend-driven flow).
  String get fitbitAuthUrl =>
      hasParticipant ? _api.getFitbitAuthUrl(_participantId) : '';

  // ── Sync ─────────────────────────────────────────────────

  Future<void> fetchSyncStatus() async {
    try {
      syncStatus = await _api.getSyncStatus();
    } catch (e) {
      syncStatus = null;
    }
    notifyListeners();
  }

  Future<Map<String, dynamic>> triggerSync() async {
    if (!hasParticipant) return {'error': 'No participant set'};
    final result = await _api.syncParticipant(_participantId);
    await fetchSyncStatus();
    return result;
  }

  Future<Map<String, dynamic>> triggerSyncAll() async {
    final result = await _api.syncAll();
    await fetchSyncStatus();
    return result;
  }

  // ── Affect inference ─────────────────────────────────────

  Future<void> fetchAffectState() async {
    if (!hasParticipant) return;
    try {
      affectState = await _api.getAffectState(_participantId);
    } catch (e) {
      affectState = null;
    }
    notifyListeners();
  }

  Future<AffectState?> runAffectInference() async {
    if (!hasParticipant) return null;
    try {
      affectState = await _api.runAffectInference(_participantId);
      notifyListeners();
      return affectState;
    } catch (e) {
      _error = 'Affect: $e';
      notifyListeners();
      return null;
    }
  }

  // ── EMA ──────────────────────────────────────────────────

  Future<void> fetchEMALabels() async {
    if (!hasParticipant) return;
    try {
      emaLabels = await _api.getEMALabels(_participantId);
    } catch (e) {
      // Non-critical
    }
    notifyListeners();
  }

  Future<void> submitEMA({
    int? arousal,
    int? valence,
    int? stress,
    String? emotionTag,
    String contextNote = '',
  }) async {
    if (!hasParticipant) return;
    await _api.submitEMA(
      participantId: _participantId,
      arousal: arousal,
      valence: valence,
      stress: stress,
      emotionTag: emotionTag,
      contextNote: contextNote,
    );
    await fetchEMALabels();
  }

  // ── Data streaming (dataset or live) ───────────────────

  /// Start streaming data for the current participant.
  /// Uses LifeSnaps dataset replay or live Fitbit API depending on data source.
  Future<void> startStreaming({double speed = 10.0}) async {
    if (!hasParticipant) return;
    _streaming = true;
    _streamError = null;
    notifyListeners();
    try {
      if (_useDataset) {
        await _api.startLifeSnapsStream(_participantId, speed: speed);
      } else {
        await _api.startLiveFitbitStream(_participantId);
      }
    } catch (e) {
      _streamError = e.toString();
      _streaming = false;
    }
    notifyListeners();
  }

  void stopStreaming() {
    _streaming = false;
    _streamError = null;
    notifyListeners();
  }

  // ── System info ──────────────────────────────────────────

  Future<void> fetchSystemInfo() async {
    try {
      systemInfo = await _api.getSystemInfo();
    } catch (e) {
      systemInfo = null;
    }
    notifyListeners();
  }

  void clearError() {
    _error = null;
    notifyListeners();
  }

  /// Update the server URL, persist it, and reconnect.
  Future<void> setServerUrl(String url) async {
    await AppConfig.setBaseUrl(url);
    _api = ApiClient(baseUrl: AppConfig.baseUrl);
    notifyListeners();
    if (hasParticipant) {
      await refreshAll();
    }
  }
}
