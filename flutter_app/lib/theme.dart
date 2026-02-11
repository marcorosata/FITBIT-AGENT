/// Shared theme constants for the Wearable Agent app.
library;

import 'package:flutter/material.dart';

class AppTheme {
  AppTheme._();

  // Brand colours (matching the web UI)
  static const Color accent = Color(0xFF6C5CE7);
  static const Color accentLight = Color(0xFFA29BFE);
  static const Color success = Color(0xFF00B894);
  static const Color warning = Color(0xFFF39C12);
  static const Color danger = Color(0xFFE74C3C);
  static const Color critical = Color(0xFFC0392B);
  static const Color info = Color(0xFF0984E3);
  static const Color bg = Color(0xFFF5F6FA);
  static const Color surface = Colors.white;
  static const Color textPrimary = Color(0xFF2D3436);
  static const Color textSecondary = Color(0xFF636E72);
  static const Color border = Color(0xFFE8EAF0);

  static ThemeData get light => ThemeData(
        useMaterial3: true,
        colorSchemeSeed: accent,
        brightness: Brightness.light,
        scaffoldBackgroundColor: bg,
        cardTheme: const CardTheme(
          elevation: 0,
          color: surface,
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.all(Radius.circular(16)),
          ),
        ),
        appBarTheme: const AppBarTheme(
          backgroundColor: accent,
          foregroundColor: Colors.white,
          elevation: 0,
        ),
      );

  /// Severity → colour
  static Color severityColor(String severity) {
    switch (severity.toLowerCase()) {
      case 'critical':
        return critical;
      case 'warning':
        return warning;
      case 'info':
        return info;
      default:
        return textSecondary;
    }
  }

  /// Severity → icon
  static IconData severityIcon(String severity) {
    switch (severity.toLowerCase()) {
      case 'critical':
        return Icons.error;
      case 'warning':
        return Icons.warning_amber_rounded;
      case 'info':
        return Icons.info_outline;
      default:
        return Icons.notifications_none;
    }
  }

  /// Metric → icon
  static IconData metricIcon(String metric) {
    switch (metric) {
      case 'heart_rate':
        return Icons.favorite;
      case 'steps':
        return Icons.directions_walk;
      case 'sleep':
        return Icons.bedtime;
      case 'spo2':
        return Icons.air;
      case 'hrv':
        return Icons.timeline;
      case 'calories':
        return Icons.local_fire_department;
      case 'skin_temperature':
        return Icons.thermostat;
      case 'breathing_rate':
        return Icons.waves;
      case 'body_weight':
        return Icons.monitor_weight;
      case 'body_fat':
        return Icons.percent;
      case 'distance':
        return Icons.straighten;
      case 'floors':
        return Icons.stairs;
      case 'vo2_max':
        return Icons.speed;
      case 'active_zone_minutes':
        return Icons.timer;
      default:
        return Icons.sensors;
    }
  }

  /// Metric → colour
  static Color metricColor(String metric) {
    switch (metric) {
      case 'heart_rate':
        return danger;
      case 'steps':
        return success;
      case 'sleep':
        return const Color(0xFF6C5CE7);
      case 'spo2':
        return info;
      case 'hrv':
        return const Color(0xFFE17055);
      case 'calories':
        return warning;
      case 'skin_temperature':
        return const Color(0xFFE84393);
      default:
        return accent;
    }
  }
}
