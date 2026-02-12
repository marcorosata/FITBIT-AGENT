/// Today screen — Fitbit-style health dashboard with metric cards & chart.
library;

import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'package:fl_chart/fl_chart.dart';
import '../animations.dart';
import '../app_state.dart';
import '../theme.dart';

class DashboardScreen extends StatefulWidget {
  const DashboardScreen({super.key});

  @override
  State<DashboardScreen> createState() => _DashboardScreenState();
}

class _DashboardScreenState extends State<DashboardScreen> {
  static const _metrics = [
    'hrv',
    'resting_heart_rate',
    'stress',
    'skin_temperature',
    'breathing_rate',
    'sleep_efficiency',
    'distance',
    'vo2_max',
    'heart_rate',
    'steps',
    'sleep',
    'spo2',
    'calories',
  ];

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return Consumer<AppState>(
      builder: (context, state, _) {
        if (!state.hasParticipant) {
          return _EmptyState(theme: theme);
        }

        if (state.loading) {
          return Center(
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                const CircularProgressIndicator(),
                const SizedBox(height: 16),
                Text('Loading your health data...',
                    style: theme.textTheme.bodyMedium?.copyWith(
                        color: theme.colorScheme.onSurface.withOpacity(0.5))),
              ],
            ),
          );
        }

        return RefreshIndicator(
          onRefresh: state.refreshAll,
          color: AppTheme.fitbitTeal,
          child: ListView(
            padding: const EdgeInsets.fromLTRB(16, 8, 16, 24),
            children: [
              // ── Metric selector ──
              SizedBox(
                height: 40,
                child: ListView.separated(
                  scrollDirection: Axis.horizontal,
                  itemCount: _metrics.length,
                  separatorBuilder: (_, __) => const SizedBox(width: 8),
                  itemBuilder: (context, i) {
                    final m = _metrics[i];
                    final selected = m == state.selectedMetric;
                    final color = AppTheme.metricColor(m);
                    return GestureDetector(
                      onTap: () => state.setMetric(m),
                      child: AnimatedContainer(
                        duration: const Duration(milliseconds: 200),
                        padding: const EdgeInsets.symmetric(
                            horizontal: 14, vertical: 8),
                        decoration: BoxDecoration(
                          color: selected
                              ? color.withOpacity(0.12)
                              : theme.colorScheme.surfaceContainerHighest,
                          borderRadius: BorderRadius.circular(20),
                          border: Border.all(
                            color: selected
                                ? color.withOpacity(0.4)
                                : theme.colorScheme.outline,
                            width: selected ? 1.5 : 1,
                          ),
                        ),
                        child: Row(
                          mainAxisSize: MainAxisSize.min,
                          children: [
                            Icon(
                              AppTheme.metricIcon(m),
                              size: 14,
                              color: selected
                                  ? color
                                  : theme.colorScheme.onSurface
                                      .withOpacity(0.4),
                            ),
                            const SizedBox(width: 6),
                            Text(
                              AppTheme.metricLabel(m),
                              style: TextStyle(
                                fontSize: 12,
                                fontWeight: selected
                                    ? FontWeight.w600
                                    : FontWeight.w400,
                                color: selected
                                    ? color
                                    : theme.colorScheme.onSurface
                                        .withOpacity(0.5),
                              ),
                            ),
                          ],
                        ),
                      ),
                    );
                  },
                ),
              ),
              const SizedBox(height: 16),

              // ── Stats row ──
              if (state.stats != null)
                StaggeredFadeSlide(
                  index: 0,
                  child: Row(
                    children: [
                      _StatCard(
                        'Readings',
                        state.stats!.totalReadings.toString(),
                        Icons.show_chart_rounded,
                        AppTheme.fitbitTeal,
                      ),
                      const SizedBox(width: 10),
                      _StatCard(
                        'Alerts',
                        state.stats!.totalAlerts.toString(),
                        Icons.notifications_rounded,
                        AppTheme.fitbitOrange,
                      ),
                      const SizedBox(width: 10),
                      _StatCard(
                        'Users',
                        state.stats!.participants.length.toString(),
                        Icons.people_rounded,
                        AppTheme.fitbitBlue,
                      ),
                    ],
                  ),
                ),
              const SizedBox(height: 16),

              // ── Stream button ──
              StaggeredFadeSlide(
                index: 1,
                child: _StreamDataButton(),
              ),
              const SizedBox(height: 16),

              // ── Chart card ──
              StaggeredFadeSlide(
                index: 2,
                child: Container(
                  decoration: AppTheme.healthCard(context),
                  padding: const EdgeInsets.all(16),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Row(
                        children: [
                          Icon(
                            AppTheme.metricIcon(state.selectedMetric),
                            color: AppTheme.metricColor(state.selectedMetric),
                            size: 18,
                          ),
                          const SizedBox(width: 8),
                          Text(
                            AppTheme.metricLabel(state.selectedMetric),
                            style: theme.textTheme.titleMedium,
                          ),
                          const Spacer(),
                          Container(
                            padding: const EdgeInsets.symmetric(
                                horizontal: 8, vertical: 4),
                            decoration: BoxDecoration(
                              color: theme.colorScheme.surfaceContainerHighest,
                              borderRadius: BorderRadius.circular(8),
                            ),
                            child: Text(
                              '${state.readings.length} pts',
                              style: theme.textTheme.labelSmall,
                            ),
                          ),
                        ],
                      ),
                      const SizedBox(height: 16),
                      SizedBox(
                        height: 200,
                        child: state.readings.isEmpty
                            ? Center(
                                child: Text(
                                  'No data available',
                                  style: theme.textTheme.bodySmall,
                                ),
                              )
                            : _buildChart(state, theme),
                      ),
                    ],
                  ),
                ),
              ),
              const SizedBox(height: 16),

              // ── Recent readings ──
              StaggeredFadeSlide(
                index: 3,
                child: Container(
                  decoration: AppTheme.healthCard(context),
                  padding: const EdgeInsets.all(16),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text('Recent Readings',
                          style: theme.textTheme.titleMedium),
                      const SizedBox(height: 12),
                      if (state.readings.isEmpty)
                        Padding(
                          padding: const EdgeInsets.symmetric(vertical: 24),
                          child: Center(
                            child: Text('No readings yet',
                                style: theme.textTheme.bodySmall),
                          ),
                        )
                      else
                        ...state.readings.take(10).map((r) => Container(
                              padding: const EdgeInsets.symmetric(vertical: 8),
                              decoration: BoxDecoration(
                                border: Border(
                                  bottom: BorderSide(
                                    color: theme.colorScheme.outline
                                        .withOpacity(0.3),
                                  ),
                                ),
                              ),
                              child: Row(
                                mainAxisAlignment:
                                    MainAxisAlignment.spaceBetween,
                                children: [
                                  Text(
                                    '${r.value} ${r.unit}',
                                    style: theme.textTheme.bodyMedium?.copyWith(
                                      fontWeight: FontWeight.w600,
                                    ),
                                  ),
                                  Text(
                                    _formatTimestamp(r.timestamp),
                                    style: theme.textTheme.labelSmall,
                                  ),
                                ],
                              ),
                            )),
                    ],
                  ),
                ),
              ),
              const SizedBox(height: 16),

              // ── Affect state ──
              if (state.affectState != null)
                StaggeredFadeSlide(
                  index: 4,
                  child: Container(
                    decoration: AppTheme.healthCard(context),
                    padding: const EdgeInsets.all(16),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Row(
                          children: [
                            Text('Wellbeing',
                                style: theme.textTheme.titleMedium),
                            const Spacer(),
                            IconButton(
                              icon: Icon(Icons.refresh_rounded,
                                  size: 20,
                                  color: theme.colorScheme.onSurface
                                      .withOpacity(0.4)),
                              onPressed: () => state.runAffectInference(),
                              tooltip: 'Re-run inference',
                            ),
                          ],
                        ),
                        const SizedBox(height: 12),
                        Row(
                          children: [
                            _WellbeingChip(
                                'Arousal',
                                state.affectState!.arousal.toStringAsFixed(1),
                                AppTheme.fitbitCoral),
                            const SizedBox(width: 8),
                            _WellbeingChip(
                                'Valence',
                                state.affectState!.valence.toStringAsFixed(1),
                                AppTheme.fitbitGreen),
                            const SizedBox(width: 8),
                            _WellbeingChip(
                                'Stress',
                                state.affectState!.stress.toStringAsFixed(1),
                                AppTheme.fitbitOrange),
                          ],
                        ),
                        if (state.affectState!.emotion != null) ...[
                          const SizedBox(height: 10),
                          Text(
                            'Detected: ${state.affectState!.emotion} (${state.affectState!.confidence})',
                            style: theme.textTheme.bodySmall,
                          ),
                        ],
                      ],
                    ),
                  ),
                )
              else if (state.hasParticipant)
                StaggeredFadeSlide(
                  index: 4,
                  child: Container(
                    decoration: AppTheme.healthCard(context),
                    padding: const EdgeInsets.all(16),
                    child: Column(
                      children: [
                        Text('No wellbeing data yet',
                            style: theme.textTheme.bodySmall),
                        const SizedBox(height: 10),
                        SizedBox(
                          width: double.infinity,
                          child: OutlinedButton.icon(
                            icon:
                                const Icon(Icons.psychology_rounded, size: 16),
                            label: const Text('Run Wellbeing Check'),
                            onPressed: () => state.runAffectInference(),
                          ),
                        ),
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

  Widget _buildChart(AppState state, ThemeData theme) {
    final data = state.readings.reversed.toList();
    final spots = <FlSpot>[];
    for (var i = 0; i < data.length; i++) {
      spots.add(FlSpot(i.toDouble(), data[i].value));
    }
    final color = AppTheme.metricColor(state.selectedMetric);

    return LineChart(
      LineChartData(
        gridData: FlGridData(
          show: true,
          drawVerticalLine: false,
          getDrawingHorizontalLine: (value) => FlLine(
            color: theme.colorScheme.outline.withOpacity(0.2),
            strokeWidth: 0.5,
          ),
        ),
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
              gradient: LinearGradient(
                begin: Alignment.topCenter,
                end: Alignment.bottomCenter,
                colors: [
                  color.withOpacity(0.20),
                  color.withOpacity(0.0),
                ],
              ),
            ),
          ),
        ],
        lineTouchData: LineTouchData(
          touchTooltipData: LineTouchTooltipData(
            tooltipRoundedRadius: 10,
            getTooltipItems: (spots) => spots
                .map((s) => LineTooltipItem(
                      s.y.toStringAsFixed(1),
                      TextStyle(
                        color: color,
                        fontWeight: FontWeight.bold,
                        fontSize: 13,
                      ),
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

// ── Empty state ──

class _EmptyState extends StatelessWidget {
  final ThemeData theme;
  const _EmptyState({required this.theme});

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(40),
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Container(
              padding: const EdgeInsets.all(24),
              decoration: BoxDecoration(
                color: AppTheme.fitbitTeal.withOpacity(0.08),
                shape: BoxShape.circle,
              ),
              child: const Icon(
                Icons.watch_rounded,
                size: 48,
                color: AppTheme.fitbitTeal,
              ),
            ),
            const SizedBox(height: 24),
            Text(
              'Welcome to Fitbit Health',
              style: theme.textTheme.headlineMedium,
              textAlign: TextAlign.center,
            ),
            const SizedBox(height: 10),
            Text(
              'Go to Profile to set your Participant ID\nand start tracking your health data.',
              textAlign: TextAlign.center,
              style: theme.textTheme.bodyMedium?.copyWith(
                color: theme.colorScheme.onSurface.withOpacity(0.5),
                height: 1.6,
              ),
            ),
          ],
        ),
      ),
    );
  }
}

// ── Stat card ──

class _StatCard extends StatelessWidget {
  final String label;
  final String value;
  final IconData icon;
  final Color color;

  const _StatCard(this.label, this.value, this.icon, this.color);

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Expanded(
      child: Container(
        decoration: AppTheme.accentCard(context, color),
        padding: const EdgeInsets.symmetric(vertical: 16, horizontal: 10),
        child: Column(
          children: [
            Icon(icon, color: color, size: 22),
            const SizedBox(height: 10),
            Text(
              value,
              style: AppTheme.heading.copyWith(
                fontSize: 22,
                fontWeight: FontWeight.w700,
                color: color,
              ),
            ),
            const SizedBox(height: 4),
            Text(
              label,
              style: theme.textTheme.labelSmall?.copyWith(
                color: theme.colorScheme.onSurface.withOpacity(0.5),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

// ── Wellbeing chip ──

class _WellbeingChip extends StatelessWidget {
  final String label;
  final String value;
  final Color color;

  const _WellbeingChip(this.label, this.value, this.color);

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Expanded(
      child: Container(
        padding: const EdgeInsets.symmetric(vertical: 12, horizontal: 12),
        decoration: AppTheme.accentCard(context, color),
        child: Column(
          children: [
            Text(
              value,
              style: AppTheme.heading.copyWith(
                fontSize: 20,
                fontWeight: FontWeight.w700,
                color: color,
              ),
            ),
            const SizedBox(height: 4),
            Text(
              label,
              style: theme.textTheme.labelSmall?.copyWith(
                color: color.withOpacity(0.8),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

// ── Stream all data button ──

class _StreamDataButton extends StatefulWidget {
  @override
  State<_StreamDataButton> createState() => _StreamDataButtonState();
}

class _StreamDataButtonState extends State<_StreamDataButton> {
  double _speed = 10.0;

  @override
  Widget build(BuildContext context) {
    final state = context.watch<AppState>();
    final theme = Theme.of(context);
    final isStreaming = state.streaming;
    final isDataset = state.useDataset;

    // Context-aware labels
    final sourceLabel = isDataset ? 'LifeSnaps Dataset' : 'Live Fitbit';
    final sourceIcon = isDataset ? Icons.dataset_rounded : Icons.sensors_rounded;
    final actionLabel = isDataset ? 'Replay Data' : 'Sync Live Data';
    final streamingLabel = isDataset ? 'Replaying...' : 'Syncing Live...';
    final buttonLabel = isStreaming
        ? 'Stop Stream'
        : isDataset
            ? 'Stream All Data'
            : 'Fetch Live Data';

    return Container(
      decoration: AppTheme.healthCard(context),
      padding: const EdgeInsets.all(16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Icon(
                isStreaming ? Icons.stream_rounded : Icons.play_circle_rounded,
                color:
                    isStreaming ? AppTheme.fitbitCoral : AppTheme.fitbitGreen,
                size: 20,
              ),
              const SizedBox(width: 8),
              Text(
                isStreaming ? streamingLabel : actionLabel,
                style: theme.textTheme.titleMedium,
              ),
              const Spacer(),
              if (isStreaming) PulseDot(color: AppTheme.fitbitCoral),
            ],
          ),
          const SizedBox(height: 8),
          // Data source indicator
          Row(
            children: [
              Icon(sourceIcon, size: 14, color: theme.colorScheme.onSurfaceVariant),
              const SizedBox(width: 6),
              Text(
                'Source: $sourceLabel',
                style: theme.textTheme.bodySmall?.copyWith(
                  color: theme.colorScheme.onSurfaceVariant,
                ),
              ),
            ],
          ),
          const SizedBox(height: 8),
          // Speed selector (only for dataset replay)
          if (!isStreaming && isDataset)
            Padding(
              padding: const EdgeInsets.only(bottom: 12),
              child: Row(
                children: [
                  Text('Speed:', style: theme.textTheme.bodySmall),
                  const SizedBox(width: 8),
                  ...[1.0, 10.0, 50.0, 100.0].map((s) {
                    final sel = _speed == s;
                    return Padding(
                      padding: const EdgeInsets.only(right: 6),
                      child: ChoiceChip(
                        label: Text('${s.toInt()}x'),
                        selected: sel,
                        onSelected: (_) => setState(() => _speed = s),
                        visualDensity: VisualDensity.compact,
                        labelStyle: TextStyle(
                          fontSize: 11,
                          fontWeight: sel ? FontWeight.w600 : FontWeight.w400,
                        ),
                      ),
                    );
                  }),
                ],
              ),
            ),
          SizedBox(
            width: double.infinity,
            child: FilledButton.icon(
              icon: Icon(
                  isStreaming ? Icons.stop_rounded : Icons.play_arrow_rounded,
                  size: 18),
              label: Text(buttonLabel),
              style: FilledButton.styleFrom(
                backgroundColor:
                    isStreaming ? AppTheme.fitbitCoral : AppTheme.fitbitTeal,
              ),
              onPressed: isStreaming
                  ? state.stopStreaming
                  : () => state.startStreaming(speed: _speed),
            ),
          ),
          if (state.streamError != null)
            Padding(
              padding: const EdgeInsets.only(top: 8),
              child: Text(
                state.streamError!,
                style: TextStyle(fontSize: 11, color: AppTheme.fitbitCoral),
                maxLines: 2,
                overflow: TextOverflow.ellipsis,
              ),
            ),
        ],
      ),
    );
  }
}
