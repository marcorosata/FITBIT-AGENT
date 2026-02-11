/// Dashboard screen — metric cards and recent readings chart.
library;

import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'package:fl_chart/fl_chart.dart';
import '../app_state.dart';
import '../theme.dart';

class DashboardScreen extends StatefulWidget {
  const DashboardScreen({super.key});

  @override
  State<DashboardScreen> createState() => _DashboardScreenState();
}

class _DashboardScreenState extends State<DashboardScreen> {
  static const _metrics = [
    'heart_rate',
    'steps',
    'spo2',
    'hrv',
    'sleep',
    'calories',
    'skin_temperature',
    'breathing_rate',
  ];

  @override
  Widget build(BuildContext context) {
    return Consumer<AppState>(
      builder: (context, state, _) {
        if (!state.hasParticipant) {
          return const Center(
            child: Padding(
              padding: EdgeInsets.all(32),
              child: Text(
                'Enter your Participant ID in the header to get started.',
                textAlign: TextAlign.center,
                style: TextStyle(fontSize: 16, color: AppTheme.textSecondary),
              ),
            ),
          );
        }

        return RefreshIndicator(
          onRefresh: state.refreshAll,
          child: ListView(
            padding: const EdgeInsets.all(16),
            children: [
              // ── Metric selector chips ──
              SizedBox(
                height: 40,
                child: ListView.separated(
                  scrollDirection: Axis.horizontal,
                  itemCount: _metrics.length,
                  separatorBuilder: (_, __) => const SizedBox(width: 8),
                  itemBuilder: (context, i) {
                    final m = _metrics[i];
                    final selected = m == state.selectedMetric;
                    return ChoiceChip(
                      label: Text(m.replaceAll('_', ' ')),
                      selected: selected,
                      selectedColor: AppTheme.metricColor(m).withOpacity(0.2),
                      onSelected: (_) => state.setMetric(m),
                      avatar: Icon(
                        AppTheme.metricIcon(m),
                        size: 16,
                        color: AppTheme.metricColor(m),
                      ),
                    );
                  },
                ),
              ),
              const SizedBox(height: 20),

              // ── Stats summary ──
              if (state.stats != null) ...[
                Row(
                  children: [
                    _StatCard(
                      'Readings',
                      state.stats!.totalReadings.toString(),
                      Icons.show_chart,
                      AppTheme.accent,
                    ),
                    const SizedBox(width: 12),
                    _StatCard(
                      'Alerts',
                      state.stats!.totalAlerts.toString(),
                      Icons.warning_amber_rounded,
                      AppTheme.warning,
                    ),
                    const SizedBox(width: 12),
                    _StatCard(
                      'Participants',
                      state.stats!.participants.length.toString(),
                      Icons.people,
                      AppTheme.success,
                    ),
                  ],
                ),
                const SizedBox(height: 20),
              ],

              // ── Chart ──
              Card(
                child: Padding(
                  padding: const EdgeInsets.all(16),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Row(
                        children: [
                          Icon(AppTheme.metricIcon(state.selectedMetric),
                              color: AppTheme.metricColor(state.selectedMetric)),
                          const SizedBox(width: 8),
                          Text(
                            state.selectedMetric.replaceAll('_', ' ').toUpperCase(),
                            style: const TextStyle(
                                fontWeight: FontWeight.w700, fontSize: 14),
                          ),
                          const Spacer(),
                          Text(
                            '${state.readings.length} readings',
                            style: const TextStyle(
                                color: AppTheme.textSecondary, fontSize: 12),
                          ),
                        ],
                      ),
                      const SizedBox(height: 16),
                      SizedBox(
                        height: 200,
                        child: state.readings.isEmpty
                            ? const Center(child: Text('No data'))
                            : _buildChart(state),
                      ),
                    ],
                  ),
                ),
              ),
              const SizedBox(height: 16),

              // ── Recent readings list ──
              Card(
                child: Padding(
                  padding: const EdgeInsets.all(16),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      const Text('Recent Readings',
                          style: TextStyle(fontWeight: FontWeight.w700)),
                      const SizedBox(height: 8),
                      if (state.readings.isEmpty)
                        const Padding(
                          padding: EdgeInsets.symmetric(vertical: 24),
                          child: Center(
                              child: Text('No readings yet',
                                  style: TextStyle(
                                      color: AppTheme.textSecondary))),
                        )
                      else
                        ...state.readings.take(15).map((r) => Padding(
                              padding: const EdgeInsets.symmetric(vertical: 4),
                              child: Row(
                                mainAxisAlignment:
                                    MainAxisAlignment.spaceBetween,
                                children: [
                                  Text(
                                    '${r.value} ${r.unit}',
                                    style: const TextStyle(
                                        fontWeight: FontWeight.w600),
                                  ),
                                  Text(
                                    _formatTimestamp(r.timestamp),
                                    style: const TextStyle(
                                        color: AppTheme.textSecondary,
                                        fontSize: 12),
                                  ),
                                ],
                              ),
                            )),
                    ],
                  ),
                ),
              ),
            ],
          ),
        );
      },
    );
  }

  Widget _buildChart(AppState state) {
    final data = state.readings.reversed.toList();
    final spots = <FlSpot>[];
    for (var i = 0; i < data.length; i++) {
      spots.add(FlSpot(i.toDouble(), data[i].value));
    }

    final color = AppTheme.metricColor(state.selectedMetric);

    return LineChart(
      LineChartData(
        gridData: const FlGridData(show: false),
        titlesData: const FlTitlesData(show: false),
        borderData: FlBorderData(show: false),
        lineBarsData: [
          LineChartBarData(
            spots: spots,
            isCurved: true,
            color: color,
            barWidth: 2.5,
            isStrokeCapRound: true,
            dotData: const FlDotData(show: false),
            belowBarData: BarAreaData(
              show: true,
              color: color.withOpacity(0.1),
            ),
          ),
        ],
        lineTouchData: LineTouchData(
          touchTooltipData: LineTouchTooltipData(
            getTooltipItems: (spots) => spots
                .map((s) => LineTooltipItem(
                      s.y.toStringAsFixed(1),
                      TextStyle(color: color, fontWeight: FontWeight.bold),
                    ))
                .toList(),
          ),
        ),
      ),
    );
  }

  String _formatTimestamp(String ts) {
    try {
      final dt = DateTime.parse(ts);
      return '${dt.hour.toString().padLeft(2, '0')}:${dt.minute.toString().padLeft(2, '0')}';
    } catch (_) {
      return ts;
    }
  }
}

class _StatCard extends StatelessWidget {
  final String label;
  final String value;
  final IconData icon;
  final Color color;

  const _StatCard(this.label, this.value, this.icon, this.color);

  @override
  Widget build(BuildContext context) {
    return Expanded(
      child: Card(
        child: Padding(
          padding: const EdgeInsets.all(14),
          child: Column(
            children: [
              Icon(icon, color: color, size: 22),
              const SizedBox(height: 6),
              Text(value,
                  style: TextStyle(
                      fontSize: 22, fontWeight: FontWeight.w700, color: color)),
              Text(label,
                  style: const TextStyle(
                      fontSize: 11, color: AppTheme.textSecondary)),
            ],
          ),
        ),
      ),
    );
  }
}
