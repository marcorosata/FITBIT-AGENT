/// Central app state managed via Provider / ChangeNotifier.
library;

import 'package:flutter/foundation.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'api_client.dart';
import 'config.dart';
import 'models.dart';

class AppState extends ChangeNotifier {
  late ApiClient _api;
  String _baseUrl = AppConfig.defaultBaseUrl;
  String _participantId = '';
  bool _loading = false;
  String? _error;

  // Cached data
  HealthStats? stats;
  List<SensorReading> readings = [];
  List<Alert> alerts = [];
  List<MonitoringRule> rules = [];
  String _selectedMetric = 'heart_rate';

  AppState() {
    _api = ApiClient(baseUrl: _baseUrl);
    _loadPrefs();
  }

  // ── Getters ──────────────────────────────────────────────

  String get baseUrl => _baseUrl;
  String get participantId => _participantId;
  bool get loading => _loading;
  String? get error => _error;
  String get selectedMetric => _selectedMetric;
  ApiClient get api => _api;
  bool get hasParticipant => _participantId.isNotEmpty;

  // ── Prefs ────────────────────────────────────────────────

  Future<void> _loadPrefs() async {
    final prefs = await SharedPreferences.getInstance();
    _baseUrl = prefs.getString(AppConfig.keyBaseUrl) ?? AppConfig.defaultBaseUrl;
    _participantId = prefs.getString(AppConfig.keyParticipantId) ?? '';
    _api = ApiClient(baseUrl: _baseUrl);
    notifyListeners();
  }

  Future<void> setBaseUrl(String url) async {
    _baseUrl = url.endsWith('/') ? url.substring(0, url.length - 1) : url;
    _api = ApiClient(baseUrl: _baseUrl);
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(AppConfig.keyBaseUrl, _baseUrl);
    notifyListeners();
  }

  Future<void> setParticipantId(String id) async {
    _participantId = id.trim();
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(AppConfig.keyParticipantId, _participantId);
    notifyListeners();
    if (_participantId.isNotEmpty) {
      await refreshAll();
    }
  }

  void setMetric(String metric) {
    _selectedMetric = metric;
    notifyListeners();
    if (hasParticipant) fetchReadings();
  }

  // ── Data fetching ────────────────────────────────────────

  Future<void> refreshAll() async {
    _loading = true;
    _error = null;
    notifyListeners();
    try {
      await Future.wait([
        fetchStats(),
        fetchReadings(),
        fetchAlerts(),
        fetchRules(),
      ]);
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

  Future<void> fetchReadings() async {
    if (!hasParticipant) return;
    try {
      readings = await _api.getReadings(_participantId, _selectedMetric);
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

  void clearError() {
    _error = null;
    notifyListeners();
  }
}
