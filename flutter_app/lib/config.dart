/// Configuration constants for the Wearable Agent app.
library;

class AppConfig {
  AppConfig._();

  /// Default backend base URL — change via Settings screen at runtime.
  static const String defaultBaseUrl = 'http://10.0.2.2:8000';

  /// SharedPreferences keys
  static const String keyBaseUrl = 'base_url';
  static const String keyParticipantId = 'participant_id';

  /// Fitbit OAuth 2.0
  static const String fitbitAuthUrl = 'https://www.fitbit.com/oauth2/authorize';
  static const String fitbitTokenUrl = 'https://api.fitbit.com/oauth2/token';
  static const String fitbitRedirectUri = 'http://localhost:8000/auth/fitbit/callback';
  static const String fitbitScopes =
      'activity heartrate location nutrition profile settings sleep social weight';
}
