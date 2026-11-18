import 'dart:convert';

import 'package:dsh_app/state/agent_phone_dashboard.dart';
import 'package:dsh_app/state/connection_state.dart';
import 'package:dsh_app/state/hosts_state.dart';
import 'package:dsh_app/state/sessions_state.dart';
import 'package:dsh_app/ui/dashboard/agent_phone_dashboard_page.dart';
import 'package:dsh_client/dsh_client.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../plugins/support/fake_plugin_host.dart';
import 'golden_harness.dart';

const _mac = HostRef.relay('dashboard-mac', name: 'Mac');

class _ActiveMac extends ActiveHostController {
  @override
  HostRef build() => _mac;
}

class _MacConnection extends RemoteConnectionController {
  _MacConnection(this.connection) : super(_mac);

  final HostConnection connection;

  @override
  Future<HostConnection?> build() async => connection;
}

class _MacClient implements DshClient {
  @override
  final DshCarrier carrier = FakePluginCarrier();

  @override
  Future<List<SessionSummary>> listSessions() async => [
    SessionSummary.fromJson({'sessionId': 'test-session'}),
  ];

  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

MockClient _dashboardHttp() => MockClient((request) async {
  final json = switch (request.url.path) {
    '/api/usage' => {
      'daily': {DateTime.now().toIso8601String().substring(0, 10): 42},
    },
    '/api/sessions' => {
      'sessions': [
        {
          'source': 'dsh',
          'id': 'test-session',
          'title': 'Test conversation',
          'project': 'Example project',
          'projectKey': '/projects/example',
          'endedAt': 42,
        },
      ],
    },
    _ => throw StateError('Unexpected request'),
  };
  return http.Response(jsonEncode(json), 200);
});

void main() {
  setUp(() => SharedPreferences.setMockInitialValues({}));

  testWidgets('shows usage and projects and requires a linked host to open a conversation', (tester) async {
    usePhoneSurface(tester);
    await tester.pumpWidget(
      goldenApp(
        home: const AgentPhoneDashboardPage(),
        brightness: Brightness.light,
        overrides: [dashboardHttpClientProvider.overrideWith((ref) => _dashboardHttp())],
      ),
    );
    await tester.pumpAndSettle();

    expect(find.text('Mac 工作台'), findsWidgets);
    expect(find.text('Token 用量'), findsOneWidget);
    expect(find.byTooltip(RegExp(r' · 42 tokens$')), findsOneWidget);
    await tester.tap(find.text('按周'));
    await tester.pumpAndSettle();
    expect(find.byTooltip(RegExp(r' – .* · 42 tokens$')), findsOneWidget);

    await tester.ensureVisible(find.text('Example project'));
    await tester.tap(find.text('Example project'));
    await tester.pumpAndSettle();
    final conversation = tester.widget<ListTile>(find.widgetWithText(ListTile, 'Test conversation'));
    expect(conversation.onTap, isNull);
  });

  testWidgets('opens a session confirmed by the linked Mac in the native conversation selection', (tester) async {
    SharedPreferences.setMockInitialValues({'agent_phone_dashboard_host': _mac.encode()});
    usePhoneSurface(tester);
    final connection = HostConnection(client: _MacClient(), isLocal: false, kind: HostKind.relay, hostId: _mac.id);
    await tester.pumpWidget(
      goldenApp(
        home: Builder(
          builder: (context) => Scaffold(
            body: TextButton(
              onPressed: () =>
                  Navigator.of(context).push(MaterialPageRoute<void>(builder: (_) => const AgentPhoneDashboardPage())),
              child: const Text('Open dashboard'),
            ),
          ),
        ),
        brightness: Brightness.light,
        overrides: [
          dashboardHttpClientProvider.overrideWith((ref) => _dashboardHttp()),
          activeHostProvider.overrideWith(_ActiveMac.new),
          activeConnectionProvider.overrideWithValue(AsyncData(connection)),
          remoteConnectionProvider(_mac).overrideWith(() => _MacConnection(connection)),
        ],
      ),
    );
    await tester.tap(find.text('Open dashboard'));
    await tester.pumpAndSettle();
    await tester.ensureVisible(find.text('Example project'));
    await tester.tap(find.text('Example project'));
    await tester.pumpAndSettle();
    await tester.ensureVisible(find.text('Test conversation'));
    await tester.tap(find.text('Test conversation'));
    await tester.pumpAndSettle();

    expect(find.byType(AgentPhoneDashboardPage), findsNothing);
    final container = ProviderScope.containerOf(tester.element(find.text('Open dashboard')));
    expect(container.read(activeHostProvider), _mac);
    expect(container.read(currentSessionProvider), 'test-session');
  });
}
