/// Settings screen — server URL, participant ID, Fitbit OAuth, rules.
library;

import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'package:url_launcher/url_launcher.dart';
import '../app_state.dart';
import '../config.dart';
import '../models.dart';
import '../theme.dart';

class SettingsScreen extends StatefulWidget {
  const SettingsScreen({super.key});

  @override
  State<SettingsScreen> createState() => _SettingsScreenState();
}

class _SettingsScreenState extends State<SettingsScreen> {
  late TextEditingController _urlCtrl;
  late TextEditingController _pidCtrl;

  @override
  void initState() {
    super.initState();
    final state = context.read<AppState>();
    _urlCtrl = TextEditingController(text: state.baseUrl);
    _pidCtrl = TextEditingController(text: state.participantId);
  }

  @override
  void dispose() {
    _urlCtrl.dispose();
    _pidCtrl.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Consumer<AppState>(
      builder: (context, state, _) {
        return ListView(
          padding: const EdgeInsets.all(16),
          children: [
            // ── Connection ──
            _SectionHeader('Connection'),
            Card(
              child: Padding(
                padding: const EdgeInsets.all(16),
                child: Column(
                  children: [
                    TextField(
                      controller: _urlCtrl,
                      decoration: const InputDecoration(
                        labelText: 'Server URL',
                        hintText: AppConfig.defaultBaseUrl,
                        prefixIcon: Icon(Icons.dns_outlined),
                        border: OutlineInputBorder(),
                      ),
                      onSubmitted: (v) => state.setBaseUrl(v.trim()),
                    ),
                    const SizedBox(height: 12),
                    TextField(
                      controller: _pidCtrl,
                      decoration: const InputDecoration(
                        labelText: 'Participant ID',
                        hintText: 'P001',
                        prefixIcon: Icon(Icons.person_outline),
                        border: OutlineInputBorder(),
                      ),
                      onSubmitted: (v) => state.setParticipant(v.trim()),
                    ),
                    const SizedBox(height: 12),
                    SizedBox(
                      width: double.infinity,
                      child: FilledButton.icon(
                        icon: const Icon(Icons.save_outlined, size: 18),
                        label: const Text('Save & Reconnect'),
                        onPressed: () {
                          state.setBaseUrl(_urlCtrl.text.trim());
                          state.setParticipant(_pidCtrl.text.trim());
                          ScaffoldMessenger.of(context).showSnackBar(
                            const SnackBar(
                              content: Text('Settings saved'),
                              duration: Duration(seconds: 2),
                            ),
                          );
                        },
                      ),
                    ),
                  ],
                ),
              ),
            ),
            const SizedBox(height: 20),

            // ── Server health ──
            _SectionHeader('Server Status'),
            Card(
              child: ListTile(
                leading: FutureBuilder<bool>(
                  future: state.api.healthCheck().then((_) => true).catchError((_) => false),
                  builder: (context, snap) {
                    if (snap.connectionState != ConnectionState.done) {
                      return const SizedBox(
                          width: 20, height: 20,
                          child: CircularProgressIndicator(strokeWidth: 2));
                    }
                    final ok = snap.data ?? false;
                    return Icon(
                      ok ? Icons.check_circle : Icons.error,
                      color: ok ? AppTheme.success : AppTheme.danger,
                    );
                  },
                ),
                title: const Text('Health Check'),
                subtitle: Text(
                  state.baseUrl.isNotEmpty ? state.baseUrl : AppConfig.defaultBaseUrl,
                  style: const TextStyle(fontSize: 12),
                ),
              ),
            ),
            const SizedBox(height: 20),

            // ── Fitbit OAuth ──
            _SectionHeader('Fitbit Account'),
            Card(
              child: Padding(
                padding: const EdgeInsets.all(16),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    const Text(
                      'Connect your Fitbit account to pull health data automatically.',
                      style: TextStyle(color: AppTheme.textSecondary, fontSize: 13),
                    ),
                    const SizedBox(height: 12),
                    SizedBox(
                      width: double.infinity,
                      child: OutlinedButton.icon(
                        icon: const Icon(Icons.watch, size: 18),
                        label: const Text('Connect Fitbit'),
                        onPressed: () => _launchFitbitOAuth(context),
                      ),
                    ),
                    const SizedBox(height: 8),
                    const Text(
                      'This will open the Fitbit login page in your browser. '
                      'After authorizing, the server handles the callback.',
                      style: TextStyle(fontSize: 11, color: AppTheme.textSecondary),
                    ),
                  ],
                ),
              ),
            ),
            const SizedBox(height: 20),

            // ── Monitoring rules ──
            _SectionHeader('Monitoring Rules'),
            if (state.rules.isEmpty)
              const Card(
                child: Padding(
                  padding: EdgeInsets.all(24),
                  child: Center(
                    child: Text('No rules configured',
                        style: TextStyle(color: AppTheme.textSecondary)),
                  ),
                ),
              )
            else
              ...state.rules.map((r) => _RuleTile(rule: r)),
            const SizedBox(height: 8),
            OutlinedButton.icon(
              icon: const Icon(Icons.refresh, size: 18),
              label: const Text('Reload Rules'),
              onPressed: state.fetchRules,
            ),
            const SizedBox(height: 40),
          ],
        );
      },
    );
  }

  Future<void> _launchFitbitOAuth(BuildContext context) async {
    // Build the Fitbit OAuth 2.0 URL.
    // Client ID must be set in the server's .env (FITBIT_CLIENT_ID).
    // For the Flutter app we just open the authorize page; the backend
    // handles the redirect_uri callback.
    const clientId = 'YOUR_CLIENT_ID'; // TODO: load from config
    final scopes = AppConfig.fitbitScopes.join('+');

    final uri = Uri.parse(
      '${AppConfig.fitbitAuthorizeUrl}'
      '?response_type=code'
      '&client_id=$clientId'
      '&scope=$scopes',
    );

    if (await canLaunchUrl(uri)) {
      await launchUrl(uri, mode: LaunchMode.externalApplication);
    } else if (context.mounted) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Could not open browser')),
      );
    }
  }
}

class _SectionHeader extends StatelessWidget {
  final String title;
  const _SectionHeader(this.title);

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 8),
      child: Text(title,
          style: const TextStyle(
              fontWeight: FontWeight.w700,
              fontSize: 13,
              color: AppTheme.textSecondary)),
    );
  }
}

class _RuleTile extends StatelessWidget {
  final MonitoringRule rule;
  const _RuleTile({required this.rule});

  @override
  Widget build(BuildContext context) {
    return Card(
      margin: const EdgeInsets.only(bottom: 8),
      child: ListTile(
        leading: Icon(
          AppTheme.metricIcon(rule.metricType),
          color: AppTheme.metricColor(rule.metricType),
        ),
        title: Text(rule.name, style: const TextStyle(fontSize: 13)),
        subtitle: Text(rule.condition,
            style: const TextStyle(
                fontFamily: 'monospace', fontSize: 11, color: AppTheme.textSecondary)),
        trailing: Container(
          padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
          decoration: BoxDecoration(
            color: AppTheme.severityColor(rule.severity).withOpacity(0.15),
            borderRadius: BorderRadius.circular(999),
          ),
          child: Text(
            rule.severity.toUpperCase(),
            style: TextStyle(
              fontSize: 10,
              fontWeight: FontWeight.w700,
              color: AppTheme.severityColor(rule.severity),
            ),
          ),
        ),
      ),
    );
  }
}
