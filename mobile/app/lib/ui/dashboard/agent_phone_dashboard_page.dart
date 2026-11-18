import 'dart:async';
import 'dart:math' as math;

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:intl/intl.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../../l10n/l10n.dart';
import '../../state/agent_phone_dashboard.dart';
import '../../state/connection_state.dart';
import '../../state/hosts_state.dart';
import '../../state/sessions_state.dart';
import '../remote/host_key_dialog.dart';
import '../remote/remote_screen.dart';
import '../shell/page_frame.dart';

class AgentPhoneDashboardPage extends ConsumerStatefulWidget {
  const AgentPhoneDashboardPage({super.key});

  @override
  ConsumerState<AgentPhoneDashboardPage> createState() => _AgentPhoneDashboardPageState();
}

class _AgentPhoneDashboardPageState extends ConsumerState<AgentPhoneDashboardPage> {
  static const _gatewayKey = 'agent_phone_dashboard_gateway';
  static const _hostKey = 'agent_phone_dashboard_host';

  Uri _gateway = Uri.parse(agentPhoneDefaultGateway);
  HostRef? _boundHost;
  bool _ready = false;
  bool _weekly = false;
  bool _opening = false;

  @override
  void initState() {
    super.initState();
    unawaited(_restore());
  }

  Future<void> _restore() async {
    final prefs = await SharedPreferences.getInstance();
    if (!mounted) return;
    final savedGateway = agentPhoneGatewayUri(prefs.getString(_gatewayKey) ?? '');
    final savedHost = HostRef.decode(prefs.getString(_hostKey));
    setState(() {
      _gateway = savedGateway ?? _gateway;
      _boundHost = savedHost.isLocal ? null : savedHost;
      _ready = true;
    });
  }

  Future<void> _editGateway() async {
    final gateway = await showDialog<Uri>(
      context: context,
      builder: (_) => _GatewayDialog(initial: _gateway),
    );
    if (!mounted || gateway == null || gateway == _gateway) return;
    final prefs = await SharedPreferences.getInstance();
    await prefs.remove(_hostKey);
    await prefs.setString(_gatewayKey, gateway.origin);
    if (!mounted) return;
    setState(() {
      _gateway = gateway;
      _boundHost = null;
    });
  }

  Future<void> _bind(HostRef host) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(_hostKey, host.encode());
    if (mounted) setState(() => _boundHost = host);
  }

  Future<void> _openSession(HostRef host, AgentPhoneSession session) async {
    if (_opening) return;
    setState(() => _opening = true);
    try {
      if (ref.read(activeHostProvider) != host && !await activateHost(context, ref, host)) return;
      if (!mounted) return;
      final connection = await ref.read(remoteConnectionProvider(host).future).timeout(const Duration(seconds: 45));
      if (connection == null || connection.kind != host.kind || connection.hostId != host.id) {
        if (mounted) _notice(context.l10n.agentPhoneHostUnavailable);
        return;
      }
      final sessions = await connection.client.listSessions();
      if (!mounted) return;
      if (ref.read(activeHostProvider) != host || ref.read(activeConnectionProvider).value != connection) {
        _notice(context.l10n.agentPhoneHostUnavailable);
      } else if (!sessions.any((item) => item.sessionId == session.id)) {
        _notice(context.l10n.agentPhoneSessionMissing);
      } else {
        ref.read(currentSessionProvider.notifier).select(session.id);
        Navigator.of(context).pop();
      }
    } on Exception {
      if (mounted) _notice(context.l10n.agentPhoneHostUnavailable);
    } finally {
      if (mounted) setState(() => _opening = false);
    }
  }

  void _notice(String message) => ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(message)));

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    final active = ref.watch(activeHostProvider);
    final bound = _boundHost;
    final host = bound ?? active;
    final provider = agentPhoneDashboardProvider((_gateway, host));
    final dashboard = _ready ? ref.watch(provider) : const AsyncLoading<AgentPhoneDashboard>();
    void refresh() => ref.invalidate(provider);
    final hostName = ref.watch(hostNameProvider(host)) ?? hostLabel(host.kind, host.name);
    return AppPage.list(
      title: l10n.agentPhoneDashboard,
      actions: [
        IconButton(
          onPressed: !_ready || _opening ? null : refresh,
          tooltip: l10n.agentPhoneRefresh,
          icon: const Icon(Icons.refresh),
        ),
      ],
      children: [
        ListTile(
          leading: const Icon(Icons.dns_outlined),
          title: Text(l10n.agentPhoneGateway),
          subtitle: Text(_gateway.origin),
          trailing: const Icon(Icons.edit_outlined),
          onTap: !_ready || _opening ? null : _editGateway,
        ),
        ListTile(
          leading: const Icon(Icons.computer_outlined),
          title: Text(host.isLocal ? l10n.agentPhoneBindHost : hostName),
          subtitle: Text(
            bound != null
                ? l10n.agentPhoneBoundHost
                : (active.kind == HostKind.relay ? l10n.agentPhoneActiveHost : l10n.agentPhoneBindHint),
          ),
          onTap: _opening || !_ready
              ? null
              : () async {
                  if (active.isLocal || bound != null) {
                    await Navigator.of(context).push(MaterialPageRoute<void>(builder: (_) => const RemoteScreen()));
                    if (!mounted) return;
                  }
                  final selected = ref.read(activeHostProvider);
                  if (selected.isLocal || selected == bound) return;
                  final selectedName = ref.read(hostNameProvider(selected)) ?? hostLabel(selected.kind, selected.name);
                  final confirmed = await showDialog<bool>(
                    context: this.context,
                    builder: (dialog) => AlertDialog(
                      title: Text(l10n.agentPhoneBindHost),
                      content: Text(l10n.agentPhoneBindConfirm(selectedName)),
                      actions: [
                        TextButton(onPressed: () => Navigator.pop(dialog), child: Text(l10n.commonCancel)),
                        FilledButton(
                          onPressed: () => Navigator.pop(dialog, true),
                          child: Text(l10n.agentPhoneBindAction),
                        ),
                      ],
                    ),
                  );
                  if (confirmed == true && mounted) await _bind(selected);
                },
        ),
        if (_opening) const LinearProgressIndicator(),
        dashboard.when(
          skipLoadingOnRefresh: false,
          loading: () => const LinearProgressIndicator(),
          error: (_, _) => ListTile(
            title: Text(l10n.agentPhoneLoadFailed),
            subtitle: Text(l10n.agentPhoneNetworkHint),
            trailing: TextButton(onPressed: refresh, child: Text(l10n.agentPhoneRefresh)),
          ),
          data: (data) {
            final sessionHost = data.viaRemote ? host : bound;
            final number = NumberFormat.decimalPattern(Localizations.localeOf(context).toString());
            return Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const Divider(),
                ListTile(title: Text(l10n.agentPhoneUsage), subtitle: Text(l10n.agentPhoneUsageHint)),
                if (data.today case final today?)
                  ListTile(title: Text(l10n.agentPhoneToday), trailing: Text(number.format(today))),
                if (data.total case final total?)
                  ListTile(title: Text(l10n.agentPhoneTotal), trailing: Text(number.format(total))),
                Padding(
                  padding: const EdgeInsets.fromLTRB(16, 0, 16, 12),
                  child: SegmentedButton<bool>(
                    segments: [
                      ButtonSegment(value: false, label: Text(l10n.agentPhoneDaily)),
                      ButtonSegment(value: true, label: Text(l10n.agentPhoneWeekly)),
                    ],
                    selected: {_weekly},
                    onSelectionChanged: (selection) => setState(() => _weekly = selection.single),
                  ),
                ),
                _ActivityChart(daily: data.daily, weekly: _weekly),
                const Divider(),
                ListTile(title: Text(l10n.agentPhoneProjects)),
                if (data.projects.isEmpty) ListTile(subtitle: Text(l10n.agentPhoneNoProjects)),
                for (final project in data.projects.take(20))
                  ExpansionTile(
                    key: PageStorageKey(project.path.isEmpty ? project.name : project.path),
                    title: Text(project.name),
                    subtitle: project.path.isEmpty
                        ? null
                        : Text(project.path, maxLines: 1, overflow: TextOverflow.ellipsis),
                    children: [
                      for (final session in project.sessions)
                        ListTile(
                          title: Text(session.title, maxLines: 2, overflow: TextOverflow.ellipsis),
                          leading: const Icon(Icons.chat_bubble_outline),
                          onTap: sessionHost == null || _opening ? null : () => _openSession(sessionHost, session),
                        ),
                    ],
                  ),
              ],
            );
          },
        ),
      ],
    );
  }
}

class _GatewayDialog extends StatefulWidget {
  const _GatewayDialog({required this.initial});

  final Uri initial;

  @override
  State<_GatewayDialog> createState() => _GatewayDialogState();
}

class _GatewayDialogState extends State<_GatewayDialog> {
  late final _controller = TextEditingController(text: widget.initial.origin);
  bool _invalid = false;

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    return AlertDialog(
      title: Text(l10n.agentPhoneGateway),
      content: TextField(
        controller: _controller,
        keyboardType: TextInputType.url,
        decoration: InputDecoration(errorText: _invalid ? l10n.agentPhoneInvalidGateway : null),
      ),
      actions: [
        TextButton(onPressed: () => Navigator.pop(context), child: Text(l10n.commonCancel)),
        FilledButton(
          onPressed: () {
            final uri = agentPhoneGatewayUri(_controller.text);
            if (uri == null) {
              setState(() => _invalid = true);
            } else {
              Navigator.pop(context, uri);
            }
          },
          child: Text(l10n.commonSave),
        ),
      ],
    );
  }
}

class _ActivityChart extends StatelessWidget {
  const _ActivityChart({required this.daily, required this.weekly});

  final Map<String, int> daily;
  final bool weekly;

  @override
  Widget build(BuildContext context) {
    final today = DateTime.now();
    final date = DateTime.utc(today.year, today.month, today.day);
    final firstMonday = date.subtract(Duration(days: date.weekday - 1 + 52 * 7));
    final scheme = Theme.of(context).colorScheme;
    final numbers = NumberFormat.decimalPattern(Localizations.localeOf(context).toString());
    final weeks = List.generate(53, (week) {
      final monday = firstMonday.add(Duration(days: week * 7));
      return List.generate(7, (day) {
        final current = monday.add(Duration(days: day));
        final label = current.toIso8601String().substring(0, 10);
        return (label: label, tokens: daily[label] ?? 0);
      });
    });
    final columns = [
      for (final week in weeks)
        if (weekly)
          [
            (
              label: '${week.first.label} – ${week.last.label}',
              tokens: week.fold(0, (total, day) => total + day.tokens),
            ),
          ]
        else
          week,
    ];
    final peak = columns.expand((column) => column).fold(0, (max, day) => math.max(max, day.tokens));
    return SingleChildScrollView(
      scrollDirection: Axis.horizontal,
      reverse: true,
      padding: const EdgeInsets.fromLTRB(16, 0, 16, 12),
      child: Row(
        children: [
          for (final column in columns)
            Column(
              children: [
                for (final cell in column)
                  Tooltip(
                    message: '${cell.label} · ${numbers.format(cell.tokens)} tokens',
                    child: Container(
                      width: 12,
                      height: weekly ? 28 : 12,
                      margin: const EdgeInsets.all(1.5),
                      decoration: BoxDecoration(
                        borderRadius: BorderRadius.circular(3),
                        color: cell.tokens > 0
                            ? scheme.primary.withValues(alpha: 0.22 + 0.78 * math.sqrt(cell.tokens / peak))
                            : scheme.surfaceContainerHigh,
                      ),
                    ),
                  ),
              ],
            ),
        ],
      ),
    );
  }
}
