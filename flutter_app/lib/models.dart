/// Data models mirroring the FastAPI backend schemas.
library;

class SensorReading {
  final String id;
  final double value;
  final String unit;
  final String timestamp;
  final String deviceType;

  const SensorReading({
    required this.id,
    required this.value,
    required this.unit,
    required this.timestamp,
    required this.deviceType,
  });

  factory SensorReading.fromJson(Map<String, dynamic> json) {
    return SensorReading(
      id: json['id'] as String? ?? '',
      value: (json['value'] as num).toDouble(),
      unit: json['unit'] as String? ?? '',
      timestamp: json['timestamp'] as String? ?? '',
      deviceType: json['device_type'] as String? ?? json['device'] as String? ?? '',
    );
  }
}

class Alert {
  final String id;
  final String severity;
  final String metric;
  final String message;
  final double value;
  final String timestamp;
  final String? participantId;

  const Alert({
    required this.id,
    required this.severity,
    required this.metric,
    required this.message,
    required this.value,
    required this.timestamp,
    this.participantId,
  });

  factory Alert.fromJson(Map<String, dynamic> json) {
    return Alert(
      id: json['id'] as String? ?? '',
      severity: json['severity'] as String? ?? 'info',
      metric: json['metric'] as String? ?? '',
      message: json['message'] as String? ?? '',
      value: (json['value'] as num?)?.toDouble() ?? 0,
      timestamp: json['timestamp'] as String? ?? '',
      participantId: json['participant_id'] as String?,
    );
  }
}

class HealthStats {
  final int totalReadings;
  final int totalAlerts;
  final List<String> participants;
  final List<Alert> recentAlerts;

  const HealthStats({
    required this.totalReadings,
    required this.totalAlerts,
    required this.participants,
    required this.recentAlerts,
  });

  factory HealthStats.fromJson(Map<String, dynamic> json) {
    return HealthStats(
      totalReadings: json['total_readings'] as int? ?? 0,
      totalAlerts: json['total_alerts'] as int? ?? 0,
      participants: (json['participants'] as List<dynamic>?)
              ?.map((e) => e as String)
              .toList() ??
          [],
      recentAlerts: (json['recent_alerts'] as List<dynamic>?)
              ?.map((e) => Alert.fromJson(e as Map<String, dynamic>))
              .toList() ??
          [],
    );
  }
}

class MonitoringRule {
  final String ruleId;
  final String metricType;
  final String condition;
  final String severity;
  final String messageTemplate;

  const MonitoringRule({
    required this.ruleId,
    required this.metricType,
    required this.condition,
    required this.severity,
    required this.messageTemplate,
  });

  factory MonitoringRule.fromJson(Map<String, dynamic> json) {
    return MonitoringRule(
      ruleId: json['rule_id'] as String? ?? '',
      metricType: json['metric_type'] as String? ?? '',
      condition: json['condition'] as String? ?? '',
      severity: json['severity'] as String? ?? 'warning',
      messageTemplate: json['message_template'] as String? ?? '',
    );
  }
}
