// Measured, not eyeballed (docs/design/polish-guide.md §1): the 解除限制
// confirmation's hold key and disclaimer, the 「已解除限制」 tag, 确认方式's
// 「这些由你来操作」 lines, and first run's 确认方式 sheet.

import 'package:dsh_app/state/phone_state.dart';
import 'package:dsh_app/ui/phone/hold_to_confirm.dart';
import 'package:dsh_app/ui/phone/phone_unlock_page.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'harness.dart';

void main() {
  setUp(() => SharedPreferences.setMockInitialValues({}));

  for (final (name, size, scale) in [
    ('phone', const Size(390, 844), 1.0),
    ('320 dp × 2', const Size(320, 900), 2.0),
  ]) {
    testWidgets('the hold key: equal gutters, its label centred, nothing overflows ($name)', (tester) async {
      tester.platformDispatcher.textScaleFactorTestValue = scale;
      addTearDown(tester.platformDispatcher.clearTextScaleFactorTestValue);
      await pumpPhone(tester, const PhoneUnlockConfirmPage(unlock: PhoneUnlock.systemPages), size: size);
      final key = tester.getRect(find.byType(HoldToConfirmButton));
      expect(key.left, closeTo(size.width - key.right, 0.5));
      expect(key.left, 16);
      expect(key.height, HoldToConfirmButton.height);
      // Both faces' labels sit on the key's centre, the filled one exactly over the other.
      final faces = find.descendant(of: find.byType(HoldToConfirmButton), matching: find.byType(Text));
      expect(faces, findsNWidgets(2));
      final label = tester.getRect(faces.first);
      expect(label.center.dx, closeTo(key.center.dx, 0.5));
      expect(label.center.dy, closeTo(key.center.dy, 0.5));
      expect(tester.getRect(faces.last), label);
      // The disclaimer lines up with the cards above it.
      await tester.scrollUntilVisible(
        find.byKey(const ValueKey('unlock-disclaimer')),
        200,
        scrollable: find.byType(Scrollable).first,
      );
      final card = tester.getRect(find.byKey(const ValueKey('unlock-disclaimer')));
      expect(card.left, 16);
      expect(card.right, closeTo(size.width - 16, 0.5));
      expect(tester.takeException(), isNull);
    });
  }

}
