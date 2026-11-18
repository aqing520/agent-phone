// Neutral, asset-free activity pulse. The historic slot name remains for UI config compatibility.

import 'dart:math' as math;

import 'package:flutter/scheduler.dart';
import 'package:flutter/widgets.dart';

/// DeepSeek 官方蓝。浅色玻璃上约 3.9–4.3:1(图形的 3:1 线以上)。
const deepSeekBlue = Color(0xFF4D6BFE);

/// 深色模式的提亮版:同色相,OKLCH(0.70, 0.15, 270),在深色页面和玻璃
/// (#14171E–#343944)上 4.2–6:1。只给图形用,文字仍用 onSurface。
const deepSeekBlueDark = Color(0xFF7A98FB);

/// 按亮度取鲸尾的默认颜色。
Color whaleColorFor(Brightness brightness) => brightness == Brightness.dark ? deepSeekBlueDark : deepSeekBlue;

class WhaleTail extends StatefulWidget {
  const WhaleTail({super.key, this.level = 1, required this.color, this.height = 20, this.still = false});

  final int level;
  final Color color;

  /// 帧的高度;宽度按帧比例(5:4)。
  final double height;

  /// 不动:静止的那一帧,没有计时器。
  final bool still;

  @override
  State<WhaleTail> createState() => WhaleTailState();
}

class WhaleTailState extends State<WhaleTail> with SingleTickerProviderStateMixin {
  late final Ticker _ticker = createTicker(_onTick);
  final _repaint = ValueNotifier<int>(0);
  bool _reduced = false;

  /// 交叉淡变的时长。
  static const _blend = Duration(milliseconds: 320);

  /// 速度追向目标的时间常数(秒)。
  static const _ease = 0.35;

  /// 正在游的那一套([_from] 是淡出中的上一套,淡完为 null)。
  int _form = 2;
  int? _from;
  double _mix = 1;

  /// 每一套各自的进度(帧,含小数):淡变时两套都在走。
  final _phase = <int, double>{};

  double _rate = 0;
  Duration _last = Duration.zero;

  static int formOf(int level) => level <= 2 ? 2 : level.clamp(2, 4);

  static double rateOf(int level) => switch (level) {
    <= 0 => 0.3,
    1 => 0.5,
    _ => 1.0,
  };

  @override
  void initState() {
    super.initState();
    _form = formOf(widget.level);
    _rate = rateOf(widget.level);
  }

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    _reduced = MediaQuery.maybeDisableAnimationsOf(context) ?? false;
    _sync();
  }

  @override
  void didUpdateWidget(WhaleTail oldWidget) {
    super.didUpdateWidget(oldWidget);
    final form = formOf(widget.level);
    if (form != _form) {
      // Mid-blend: the fading one goes, the shown one becomes the old one.
      _from = _form;
      _form = form;
      _mix = 0;
    }
    _sync();
  }

  @override
  void dispose() {
    _ticker.dispose();
    _repaint.dispose();
    super.dispose();
  }

  bool get _moving => !widget.still && !_reduced;

  /// 正在游的那一套;静止时为 1(静止图)。
  @visibleForTesting
  int get shownForm => _moving ? _form : 1;

  /// 当前速度倍数(朝 [WhaleTail.level] 的目标缓过去)。
  @visibleForTesting
  double get rate => _rate;

  /// 当前这一套游到第几帧(取整)。
  @visibleForTesting
  int get frame => (_phase[_form] ?? 0).floor();

  /// Ticks whenever it moves.
  void _sync() {
    final moving = _moving;
    if (moving && !_ticker.isActive) {
      _last = Duration.zero;
      _ticker.start();
    } else if (!moving && _ticker.isActive) {
      _ticker.stop();
      _repaint.value++;
    }
  }

  void _onTick(Duration elapsed) {
    final dt = (elapsed - _last).inMicroseconds / 1e6;
    _last = elapsed;
    if (dt <= 0) return;
    final target = rateOf(widget.level);
    _rate += (target - _rate) * (1 - math.exp(-dt / _ease));
    for (final form in [_form, ?_from]) {
      final step = dt * (form + 10) * _rate;
      _phase[form] = ((_phase[form] ?? 0) + step) % 24;
    }
    if (_from != null) {
      _mix += dt * 1e6 / _blend.inMicroseconds;
      if (_mix >= 1) {
        _mix = 1;
        _phase.remove(_from);
        _from = null;
      }
    }
    _repaint.value++;
  }

  @override
  Widget build(BuildContext context) {
    return ExcludeSemantics(
      child: SizedBox(
        width: widget.height * 1.25,
        height: widget.height,
        child: CustomPaint(
          painter: _PulsePainter(state: this, repaint: _repaint, color: widget.color),
        ),
      ),
    );
  }

  /// Cross-fade the old and new pulse forms when the speed band changes.
  List<(int, double, double)> _layers() {
    if (!_moving) return const [(1, 0, 1)];
    return [
      if (_from case final from?) (from, _phase[from] ?? 0, 1 - _mix),
      (_form, _phase[_form] ?? 0, _from == null ? 1 : _mix),
    ];
  }
}

class _PulsePainter extends CustomPainter {
  _PulsePainter({required this.state, required Listenable repaint, required this.color}) : super(repaint: repaint);

  final WhaleTailState state;
  final Color color;

  @override
  void paint(Canvas canvas, Size size) {
    final paint = Paint();
    for (final (form, phase, weight) in state._layers()) {
      for (var i = 0; i < 3; i++) {
        final wave = form == 1 ? 0.5 : (math.sin((phase / 24 - i * 0.15) * 2 * math.pi) + 1) / 2;
        final height = size.height * (0.2 + wave * (0.25 + (form - 1) * 0.12));
        final width = size.width * 0.12;
        final center = size.width * (0.28 + i * 0.22);
        paint.color = color.withValues(alpha: color.a * weight * (0.5 + 0.5 * wave));
        canvas.drawRRect(
          RRect.fromRectAndRadius(
            Rect.fromCenter(center: Offset(center, size.height / 2), width: width, height: height),
            Radius.circular(width / 2),
          ),
          paint,
        );
      }
    }
  }

  @override
  bool shouldRepaint(_PulsePainter oldDelegate) => oldDelegate.color != color || oldDelegate.state != state;
}
