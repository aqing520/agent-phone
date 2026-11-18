import 'dart:convert';

import 'package:dsh_app/state/agent_phone_dashboard.dart';
import 'package:dsh_remote/dsh_remote.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

void main() {
  test('accepts the WireGuard gateway and HTTPS origins; rejects public HTTP and credential URLs', () {
    expect(agentPhoneGatewayUri('$agentPhoneDefaultGateway/')?.origin, agentPhoneDefaultGateway);
    expect(agentPhoneGatewayUri('https://dashboard.example:8443/')?.origin, 'https://dashboard.example:8443');
    expect(agentPhoneGatewayUri('http://dashboard.example'), isNull);
    expect(agentPhoneGatewayUri('https://user:pass@dashboard.example'), isNull);
    expect(agentPhoneGatewayUri('https://dashboard.example/api'), isNull);
  });

  test('reads the v1 contract and orders DeepSeek projects and sessions by activity', () async {
    final paths = <String>[];
    Map<String, Object> row(String id, String directory, int time, {String source = 'dsh', bool archived = false}) => {
      'id': id,
      'title': id,
      'archived': archived,
      'source': source,
      'cwd': directory,
      'project': 'Project',
      'projectKey': directory,
      'endedAt': time,
    };
    final client = MockClient((request) async {
      paths.add(request.url.path);
      expect(request.method, 'GET');
      expect(request.followRedirects, isFalse);
      final payload = switch (request.url.path) {
        '/api/usage' => {
          'daily': {'2026-11-18': 31},
        },
        '/api/sessions' => {
          'sessions': [
            row('older', '/first', 1),
            row('second', '/second', 2),
            row('recent', '/first', 3),
            row('codex', '/other', 4, source: 'codex'),
            row('archived', '/other', 5, archived: true),
          ],
        },
        _ => throw StateError('Unexpected path'),
      };
      return http.Response(jsonEncode(payload), 200);
    });
    addTearDown(client.close);

    final data = await AgentPhoneDashboard.load(client, Uri.parse(agentPhoneDefaultGateway));
    expect(paths, unorderedEquals(['/api/usage', '/api/sessions']));
    expect(data.daily, {'2026-11-18': 31});
    expect(data.projects.map((project) => project.path), ['/first', '/second']);
    expect(data.projects.first.sessions.map((session) => session.id), ['recent', 'older']);
  });

  test('reads V1 usage through the paired Host’s read-only dashboard', () async {
    final rpc = _DashboardRpc();
    final dashboard = await AgentPhoneDashboard.loadRemote(RemoteHostSession(rpc: rpc, capabilities: const []));
    expect(dashboard.viaRemote, isTrue);
    expect(dashboard.today, 31);
    expect(dashboard.total, 86);
    expect(dashboard.daily, {'2026-11-18': 31});
    expect(rpc.operations, ['http.open', 'http.read', 'close']);
  });
}

class _DashboardRpc implements RemoteRpcClient {
  final operations = <String>[];

  @override
  bool get isClosed => false;

  @override
  Future<Object?> call(String method, Object? params, {Duration? timeout}) async {
    expect(method, 'loopback.call');
    final request = params as Map<String, Object?>;
    final op = request['op'] as String;
    operations.add(op);
    switch (op) {
      case 'http.open':
        expect(request['port'], 5174);
        expect(request['path'], '/api/dashboard');
        expect(request['method'], 'GET');
        return {'status': 200};
      case 'http.read':
        final payload = jsonEncode({
          'usage': {
            'daily': {'2026-11-18': 31},
            'totals': {'today': 31, 'all': 86},
          },
          'sessions': [],
        });
        return {'data': base64Encode(utf8.encode(payload)), 'done': true};
      case 'close':
        return {'closed': true};
      default:
        throw StateError('Unexpected operation $op');
    }
  }

  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}
