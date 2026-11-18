// Runs around every test file under test/: real fonts first (strict: a
// missing font fails the run), so no test measures or draws the test
// engine's box font. No binding here: tests that never pump keep real
// sockets and HTTP.

import 'dart:async';
import 'dart:io';
import 'dart:typed_data';

import 'package:dsh_app/l10n/l10n.dart';
import 'package:dsh_app/performance/performance_state.dart';
import 'package:dsh_app/pets/pet_sheets.dart';
import 'package:dsh_app/state/locale_state.dart';
import 'package:dsh_app/ui/chat/empty_actions.dart' show tipStart;
import 'package:dsh_app/ui_config/ui_config_state.dart';
import 'package:flutter_test/flutter_test.dart';

import 'support/english_preview.dart';
import 'support/quiet_performance.dart';
import 'support/test_fonts.dart';

Future<void> testExecutable(FutureOr<void> Function() testMain) async {
  await loadTestFonts();
  // The chat page's pet is drawn only where a test asks for it
  // (test/pets/): elsewhere a sheet decoding in a stray real-async window
  // would make screens flicker between with and without a pet.
  PetSheets.enabled = false;
  // The new-chat tip line starts on a random tip in the app; tests (and the
  // goldens that show the new-chat page) start on the first one.
  tipStart = (_) => 0;
  // No device facts in tests: the app reads "unavailable" at once.
  PerformanceChannel.create = QuietPerformanceChannel.new;
  defaultUiConfigSourceBuilder = (_, _) => null;
  // Tests run in Chinese (goldens and finders were made in it); English
  // tests opt in with AppLocale.use(AppLocale.en) + an English MaterialApp.
  AppLanguageController.initial = AppLanguage.zh;
  AppLocale.use(AppLocale.zhCN);
  setUpEnglishPreview();
  // Public checkouts do not carry screenshot baselines. Keep rendering and
  // behavior assertions active, but make local pixel comparison opt-in.
  if (goldenFileComparator is LocalFileComparator &&
      !autoUpdateGoldenFiles &&
      Platform.environment['DSH_TEST_COMPARE_GOLDENS'] != '1') {
    goldenFileComparator = _RenderOnlyComparator();
  }
  await testMain();
}

class _RenderOnlyComparator extends GoldenFileComparator {
  @override
  Future<bool> compare(Uint8List imageBytes, Uri golden) async => true;

  @override
  Future<void> update(Uri golden, Uint8List imageBytes) async {}
}
