/// Entry point — Provider setup + bottom-navigation shell.
library;

import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import 'app_state.dart';
import 'theme.dart';
import 'screens/dashboard_screen.dart';
import 'screens/alerts_screen.dart';
import 'screens/chat_screen.dart';
import 'screens/live_stream_screen.dart';
import 'screens/settings_screen.dart';

void main() {
  WidgetsFlutterBinding.ensureInitialized();
  runApp(const WearableAgentApp());
}

class WearableAgentApp extends StatelessWidget {
  const WearableAgentApp({super.key});

  @override
  Widget build(BuildContext context) {
    return ChangeNotifierProvider(
      create: (_) => AppState()..init(),
      child: MaterialApp(
        title: 'Wearable Agent',
        debugShowCheckedModeBanner: false,
        theme: AppTheme.light,
        home: const _AppShell(),
      ),
    );
  }
}

class _AppShell extends StatefulWidget {
  const _AppShell();

  @override
  State<_AppShell> createState() => _AppShellState();
}

class _AppShellState extends State<_AppShell> {
  int _currentIndex = 0;

  static const _screens = <Widget>[
    DashboardScreen(),
    AlertsScreen(),
    ChatScreen(),
    LiveStreamScreen(),
    SettingsScreen(),
  ];

  static const _titles = [
    'Dashboard',
    'Alerts',
    'AI Chat',
    'Live Stream',
    'Settings',
  ];

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: Text(_titles[_currentIndex]),
        actions: [
          // Participant ID chip in the header
          Consumer<AppState>(
            builder: (context, state, _) {
              if (!state.hasParticipant) return const SizedBox.shrink();
              return Padding(
                padding: const EdgeInsets.only(right: 12),
                child: Chip(
                  avatar:
                      const Icon(Icons.person, size: 16, color: AppTheme.accent),
                  label: Text(state.participantId,
                      style: const TextStyle(fontSize: 12)),
                  visualDensity: VisualDensity.compact,
                ),
              );
            },
          ),
        ],
      ),
      body: IndexedStack(index: _currentIndex, children: _screens),
      bottomNavigationBar: NavigationBar(
        selectedIndex: _currentIndex,
        onDestinationSelected: (i) => setState(() => _currentIndex = i),
        destinations: const [
          NavigationDestination(
            icon: Icon(Icons.dashboard_outlined),
            selectedIcon: Icon(Icons.dashboard),
            label: 'Dashboard',
          ),
          NavigationDestination(
            icon: Icon(Icons.notifications_outlined),
            selectedIcon: Icon(Icons.notifications),
            label: 'Alerts',
          ),
          NavigationDestination(
            icon: Icon(Icons.psychology_outlined),
            selectedIcon: Icon(Icons.psychology),
            label: 'Chat',
          ),
          NavigationDestination(
            icon: Icon(Icons.sensors_outlined),
            selectedIcon: Icon(Icons.sensors),
            label: 'Live',
          ),
          NavigationDestination(
            icon: Icon(Icons.settings_outlined),
            selectedIcon: Icon(Icons.settings),
            label: 'Settings',
          ),
        ],
      ),
    );
  }
}
