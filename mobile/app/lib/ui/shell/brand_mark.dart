import 'dart:ui' as ui;

import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart';

import '../../state/app_info.dart';
import '../theme/theme.dart';
import 'brand_glyph.g.dart';

/// The Agent Phone four-square mark.
///
/// The paths are generated from the same vector master as the native launchers.
/// [color] overrides the theme-dependent flat tint; [tile] draws the app icon.
class BrandMark extends StatelessWidget {
  const BrandMark({super.key, this.size = 28, this.color, this.tile = false});

  /// Height of the glyph (its width is [aspect] × this), or the side of the tile when
  /// [tile] is true.
  final double size;

  /// A flat tint instead of the colour glyph. Ignored on a tile.
  final Color? color;

  /// Draw the launcher tile (splash, about, update).
  final bool tile;

  /// Width / height of the glyph.
  static const aspect = BrandGlyph.aspect;

  /// The glyph's visual centre, the area centroid of its ink, as fractions of its
  /// width and height from the top left.
  static final visualCentre = Offset(
    (BrandGlyph.centroid.dx - BrandGlyph.box.left) / BrandGlyph.box.width,
    (BrandGlyph.centroid.dy - BrandGlyph.box.top) / BrandGlyph.box.height,
  );

  /// How far to move a glyph of height [size] so its visual centre, not its box,
  /// sits on the centre of the space it is centred in.
  static Offset opticalShift(double size) =>
      Offset((0.5 - visualCentre.dx) * size * aspect, (0.5 - visualCentre.dy) * size);

  @override
  Widget build(BuildContext context) {
    final style = tile
        ? _Style.tile
        : color != null
        ? _Style.mono
        : Theme.of(context).brightness == Brightness.dark
        ? _Style.dark
        : _Style.light;
    return Semantics(
      label: AppInfo.wordmark,
      image: true,
      child: CustomPaint(
        size: tile ? Size.square(size) : Size(size * aspect, size),
        painter: _BrandPainter(style, color),
      ),
    );
  }
}

enum _Style { light, dark, mono, tile }

class _BrandPainter extends CustomPainter {
  const _BrandPainter(this.style, this.color);

  final _Style style;
  final Color? color;

  @override
  void paint(Canvas canvas, Size size) {
    canvas.save();
    if (style == _Style.tile) {
      const box = BrandGlyph.tileBox;
      canvas.scale(size.width / box.width, size.height / box.height);
      canvas.translate(-box.left, -box.top);
      canvas.drawPath(
        BrandGlyph.tile,
        Paint()..shader = ui.Gradient.linear(
          const Offset(7.57, -5.87),
          const Offset(100.43, 113.87),
          const [Color(0xFF7667E1), Color(0xFF5E52C1)],
        ),
      );
    } else {
      const box = BrandGlyph.box;
      canvas.scale(size.height / box.height);
      canvas.translate(-box.left, -box.top);
    }
    final fill = switch (style) {
      _Style.light => const Color(0xFF6555BB),
      _Style.dark || _Style.tile => Colors.white,
      _Style.mono => color!,
    };
    canvas.drawPath(BrandGlyph.glyph, Paint()..color = fill);
    canvas.restore();
  }

  @override
  bool shouldRepaint(_BrandPainter old) => old.style != style || old.color != color;
}

/// The glyph and a wordmark on one line.
///
/// Everything follows the word's size (0.95 × [height] by default, times the app's
/// text scale):
/// - the glyph is [glyphScale] × the word's size tall;
/// - its visual centre ([BrandMark.visualCentre]) sits on the centre of the word's
///   main band: the x-height for a lowercase word (「dsh-go」), the cap height for
///   capitals (「DSH」);
/// - [gapScale] × the word's size separates the glyph's ink from the word.
class BrandLockup extends StatelessWidget {
  const BrandLockup({
    super.key,
    this.height = 20,
    this.fontSize,
    this.label = AppInfo.wordmark,
    this.color,
    this.glyphColor,
  });

  /// The lockup's size; the word is set at 0.95 × this unless [fontSize] is given.
  final double height;

  /// The word's size, overriding the one derived from [height].
  final double? fontSize;

  final String label;

  /// The word's colour (default: onSurface).
  final Color? color;

  /// A flat glyph tint instead of the colour glyph.
  final Color? glyphColor;

  /// Glyph height / word size.
  static const glyphScale = 1.25;

  /// Gap between the glyph and the word / word size.
  static const gapScale = 0.36;

  /// x-height and cap height of the system sans, in ems (Roboto: 1082 and 1456 of
  /// 2048 units).
  static const xHeight = 0.528;
  static const capHeight = 0.711;

  /// Height above the baseline of the line the glyph centres on, for [label] set at
  /// [size].
  static double centreRise(String label, double size) =>
      (label.contains(RegExp('[a-z]')) ? xHeight : capHeight) * size / 2;

  /// Where the word starts, from the lockup's left edge, for a word drawn at [size]
  /// (after text scaling): glyph width + gap.
  static double wordInset(double size) => size * glyphScale * BrandMark.aspect + size * gapScale;

  double get _size => fontSize ?? height * 0.95;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    // The word's drawn size: the glyph and the gap scale with the text.
    final drawn = MediaQuery.textScalerOf(context).scale(_size);
    final glyph = drawn * glyphScale;
    return Row(
      mainAxisSize: MainAxisSize.min,
      crossAxisAlignment: CrossAxisAlignment.baseline,
      textBaseline: TextBaseline.alphabetic,
      children: [
        _GlyphBaseline(
          // A baseline this far below the glyph's top puts its visual centre on the
          // word's x-height (or cap-height) centre when the row aligns baselines.
          baseline: glyph * BrandMark.visualCentre.dy + centreRise(label, drawn),
          child: BrandMark(size: glyph, color: glyphColor),
        ),
        SizedBox(width: drawn * gapScale),
        Text(
          label,
          style: AppType.wordmark(size: _size, color: color ?? scheme.onSurface),
        ),
      ],
    );
  }
}

/// Reports [baseline] as its child's alphabetic baseline.
class _GlyphBaseline extends SingleChildRenderObjectWidget {
  const _GlyphBaseline({required this.baseline, required super.child});

  final double baseline;

  @override
  RenderObject createRenderObject(BuildContext context) => _RenderGlyphBaseline(baseline);

  @override
  void updateRenderObject(BuildContext context, _RenderGlyphBaseline renderObject) {
    renderObject.baseline = baseline;
  }
}

class _RenderGlyphBaseline extends RenderProxyBox {
  _RenderGlyphBaseline(this._baseline);

  double _baseline;

  set baseline(double value) {
    if (value == _baseline) return;
    _baseline = value;
    markNeedsLayout();
  }

  @override
  double? computeDistanceToActualBaseline(TextBaseline baseline) => _baseline;

  @override
  double? computeDryBaseline(BoxConstraints constraints, TextBaseline baseline) => _baseline;
}
