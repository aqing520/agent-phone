import 'package:dsh_app/state/phone_state.dart';
import 'package:dsh_app/ui/phone/phone_background_guide.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../shell/golden_harness.dart';

void main() {
  setUp(() => SharedPreferences.setMockInitialValues({}));

  testWidgets('the help remains scrollable on a narrow screen with large text', (tester) async {
    tester.view.devicePixelRatio = 1;
    tester.view.physicalSize = const Size(320, 568);
    addTearDown(tester.view.reset);
    tester.platformDispatcher.textScaleFactorTestValue = 2;
    addTearDown(tester.platformDispatcher.clearTextScaleFactorTestValue);
    await tester.runAsync(loadGoldenFonts);
    await tester.pumpWidget(
      goldenApp(
        brightness: Brightness.light,
        home: Builder(
          builder: (context) => Scaffold(
            body: Center(
              child: FilledButton(
                onPressed: () => showPhoneBackgroundGuide(context, const PhoneDevice(manufacturer: 'vivo')),
                child: const Text('Help'),
              ),
            ),
          ),
        ),
      ),
    );
    await tester.tap(find.text('Help'));
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('phone-background-guide')), findsOneWidget);
    final dialogContext = tester.element(find.byKey(const Key('phone-background-guide')));
    expect(MediaQuery.textScalerOf(dialogContext).scale(10), 20);
    expect(tester.takeException(), isNull);
    await tester.drag(find.byType(SingleChildScrollView).last, const Offset(0, -300));
    await tester.pumpAndSettle();
    await tester.ensureVisible(find.widgetWithText(TextButton, '知道了'));
    await tester.tap(find.widgetWithText(TextButton, '知道了'));
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('phone-background-guide')), findsNothing);
    expect(tester.takeException(), isNull);
  });
}
