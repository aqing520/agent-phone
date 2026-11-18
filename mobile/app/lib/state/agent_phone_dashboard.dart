import 'dart:convert';

import 'package:dsh_remote/dsh_remote.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:http/http.dart' as http;

import 'connection_state.dart';
import 'hosts_state.dart';

const agentPhoneDefaultGateway = 'http://10.77.73.1:5173';
const _dashboardPort = 5174;

final dashboardHttpClientProvider = Provider.autoDispose<http.Client>((ref) {
  final client = http.Client();
  ref.onDispose(client.close);
  return client;
});

final agentPhoneDashboardProvider = FutureProvider.autoDispose.family<AgentPhoneDashboard, (Uri, HostRef)>((
  ref,
  key,
) async {
  final (gateway, host) = key;
  if (host.kind == HostKind.relay) {
    final connection = ref.watch(remoteConnectionProvider(host).future);
    try {
      final session = (await connection.timeout(const Duration(seconds: 15)))?.client.remoteCarrier?.session;
      if (session != null && session.capabilities.contains('loopback.http-ws.v1')) {
        return await AgentPhoneDashboard.loadRemote(session).timeout(const Duration(seconds: 15));
      }
    } on Exception {
      // An older or unavailable bridge can still be reached via the V1 gateway.
    }
  }
  if (!ref.mounted) throw StateError('Dashboard was closed');
  return AgentPhoneDashboard.load(ref.watch(dashboardHttpClientProvider), gateway);
}, retry: (_, _) => null);

Uri? agentPhoneGatewayUri(String input) {
  final uri = Uri.tryParse(input.trim());
  if (uri == null ||
      !uri.hasAuthority ||
      uri.host.isEmpty ||
      uri.userInfo.isNotEmpty ||
      (uri.path.isNotEmpty && uri.path != '/') ||
      uri.hasQuery ||
      uri.hasFragment) {
    return null;
  }
  if (uri.scheme == 'https' ||
      (uri.scheme == 'http' && const {'10.77.73.1', '127.0.0.1', 'localhost'}.contains(uri.host))) {
    return Uri.parse(uri.origin);
  }
  return null;
}

class AgentPhoneSession {
  const AgentPhoneSession({required this.id, required this.title, required this.lastActivity});

  final String id;
  final String title;
  final int lastActivity;
}

class AgentPhoneProject {
  const AgentPhoneProject({required this.name, required this.path, required this.sessions});

  final String name;
  final String path;
  final List<AgentPhoneSession> sessions;
}

class AgentPhoneDashboard {
  const AgentPhoneDashboard({
    required this.daily,
    required this.projects,
    this.today,
    this.total,
    this.viaRemote = false,
  });

  final Map<String, int> daily;
  final List<AgentPhoneProject> projects;
  final int? today;
  final int? total;
  final bool viaRemote;

  static Future<AgentPhoneDashboard> loadRemote(RemoteHostSession session) async {
    final data = await session.readLoopbackJson(_dashboardPort, '/api/dashboard');
    return _parse(data['usage'] as Map<String, dynamic>, data['sessions'] as List, viaRemote: true);
  }

  static Future<AgentPhoneDashboard> load(http.Client client, Uri gateway) async {
    Future<Map<String, dynamic>> read(String path) async {
      final request = http.Request('GET', gateway.replace(path: path))..followRedirects = false;
      final response = await http.Response.fromStream(await client.send(request));
      if (response.statusCode != 200) throw http.ClientException('HTTP ${response.statusCode}', request.url);
      return jsonDecode(utf8.decode(response.bodyBytes)) as Map<String, dynamic>;
    }

    final [usage, history] = await Future.wait([read('/api/usage'), read('/api/sessions')])
        .timeout(const Duration(seconds: 15));
    return _parse(usage, history['sessions'] as List);
  }

  static AgentPhoneDashboard _parse(Map<String, dynamic> usage, List sessions, {bool viaRemote = false}) {
    final daily = (usage['daily'] as Map<String, dynamic>).map((day, value) => MapEntry(day, (value as num).toInt()));
    final projects = <String, AgentPhoneProject>{};
    for (final row in sessions.whereType<Map<String, dynamic>>()) {
      if (row['source'] != 'dsh' || row['archived'] == true) continue;
      final id = row['id'];
      if (id is! String || id.isEmpty) continue;
      final name = row['project'] as String? ?? 'DeepSeek';
      final path = (row['projectKey'] ?? row['cwd']) as String? ?? '';
      final project = projects.putIfAbsent(
        path.isEmpty ? name : path,
        () => AgentPhoneProject(name: name, path: path, sessions: []),
      );
      project.sessions.add(
        AgentPhoneSession(
          id: id,
          title: row['title'] as String? ?? '',
          lastActivity: ((row['endedAt'] ?? row['startedAt']) as num?)?.toInt() ?? 0,
        ),
      );
    }
    for (final project in projects.values) {
      project.sessions.sort((a, b) => b.lastActivity.compareTo(a.lastActivity));
    }
    final recent = projects.values.toList()
      ..sort((a, b) => b.sessions.first.lastActivity.compareTo(a.sessions.first.lastActivity));
    final totals = usage['totals'] as Map<String, dynamic>?;
    return AgentPhoneDashboard(
      daily: daily,
      projects: recent,
      today: (totals?['today'] as num?)?.toInt(),
      total: (totals?['all'] as num?)?.toInt(),
      viaRemote: viaRemote,
    );
  }
}
