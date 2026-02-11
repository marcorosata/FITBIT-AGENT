/// Alerts screen — list of recent alerts with severity badges.
library;

import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../app_state.dart';
import '../models.dart';
import '../theme.dart';

class AlertsScreen extends StatelessWidget {
  const AlertsScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return Consumer<AppState>(
      builder: (context, state, _) {
        if (!state.hasParticipant) {
          return const Center(
            child: Text('Set a participant ID to view alerts.',
                style: TextStyle(color: AppTheme.textSecondary)),
          );
        }

        if (state.alerts.isEmpty) {
          return Center(
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                Icon(Icons.check_circle_outline,
                    size: 64, color: AppTheme.success.withOpacity(0.5)),
                const SizedBox(height: 12),
                const Text('No alerts — all clear!',
                    style: TextStyle(color: AppTheme.textSecondary, fontSize: 16)),
              ],
            ),
          );
        }

        return RefreshIndicator(
          onRefresh: state.fetchAlerts,
          child: ListView.builder(
            padding: const EdgeInsets.all(12),
            itemCount: state.alerts.length,
            itemBuilder: (context, i) => _AlertTile(alert: state.alerts[i]),
          ),
        );
      },
    );
  }
}

class _AlertTile extends StatelessWidget {
  final Alert alert;
  const _AlertTile({required this.alert});

  @override
  Widget build(BuildContext context) {
    final color = AppTheme.severityColor(alert.severity);

    return Card(
      margin: const EdgeInsets.only(bottom: 10),
      child: ListTile(
        leading: CircleAvatar(
          backgroundColor: color.withOpacity(0.15),
          child: Icon(AppTheme.severityIcon(alert.severity), color: color, size: 20),
        ),
        title: Text(
          alert.message,
          style: const TextStyle(fontSize: 13, height: 1.4),
          maxLines: 3,
          overflow: TextOverflow.ellipsis,
        ),
        subtitle: Padding(
          padding: const EdgeInsets.only(top: 6),
          child: Row(
            children: [
              _Badge(alert.severity, color),
              const SizedBox(width: 8),
              Text(
                '${alert.value} · ${_formatTs(alert.timestamp)}',
                style: const TextStyle(fontSize: 11, color: AppTheme.textSecondary),
              ),
            ],
          ),
        ),
        isThreeLine: true,
      ),
    );
  }

  String _formatTs(String ts) {
    try {
      final dt = DateTime.parse(ts);
      return '${dt.month}/${dt.day} ${dt.hour.toString().padLeft(2, '0')}:${dt.minute.toString().padLeft(2, '0')}';
    } catch (_) {
      return ts;
    }
  }
}

class _Badge extends StatelessWidget {
  final String label;
  final Color color;
  const _Badge(this.label, this.color);

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
      decoration: BoxDecoration(
        color: color.withOpacity(0.15),
        borderRadius: BorderRadius.circular(999),
      ),
      child: Text(
        label.toUpperCase(),
        style: TextStyle(
            fontSize: 10, fontWeight: FontWeight.w700, color: color),
      ),
    );
  }
}
