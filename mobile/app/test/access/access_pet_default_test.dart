import 'package:dsh_app/performance/performance_state.dart';
import 'package:dsh_app/pets/overlay_channel.dart';
import 'package:dsh_app/pets/pet_prefs.dart';
import 'package:dsh_app/pets/pet_state.dart';
import 'package:dsh_app/runtime/runtime_bridge.dart';
import 'package:dsh_app/runtime/runtime_state.dart';
import 'package:dsh_app/state/access_state.dart';
import 'package:dsh_app/state/phone_state.dart';
import 'package:dsh_app/state/settings_state.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../performance/support.dart';
import '../pets/overlay/fake_overlay_native.dart';
import '../phone/support.dart';
import '../shell/golden_harness.dart';
import 'support.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  late FakeOverlayNative pet;

  Future<ProviderContainer> container({Map<String, Object> prefs = const {}, DeviceTier tier = DeviceTier.low}) async {
    SharedPreferences.setMockInitialValues(prefs);
    FakePhoneNative(status: phoneStatus()).install();
    pet = FakeOverlayNative(permission: 'granted')..install();
    final c = ProviderContainer(
      overrides: [
        settingsProvider.overrideWith(() => FakeSettings(const AppSettings(loaded: true))),
        localRuntimeProvider.overrideWith(
          () => FakeRuntime(
            const LocalRuntimeState(loaded: true, status: RuntimeStatus(phase: RuntimePhase.notInstalled)),
          ),
        ),
        accessDriverProvider.overrideWithValue(FakeAccessDriver(offPhone)),
        performanceChannelProvider.overrideWithValue(FakePerformanceChannel(Future.value(snapshot(tier)))),
      ],
    );
    addTearDown(c.dispose);
    c.read(accessSetupProvider);
    c.read(petOverlayProvider);
    c.read(petPrefsProvider);
    await Future<void>.delayed(Duration.zero);
    await c.read(phoneProvider.notifier).refreshStatus();
    return c;
  }

  Future<String?> storedPack() async => (await SharedPreferences.getInstance()).getString(PetPrefsController.keys.pack);

  test('preparing the overlay does not select a pet before import', () async {
    final c = await container();
    await c.read(accessSetupProvider.notifier).choose({AccessFeature.pet});
    await c.read(accessSetupProvider.notifier).apply(readingsWith(offPhone, overlay: true));
    expect(c.read(petPrefsProvider).packId, noPetId);
    expect(await storedPack(), isNull);
    expect(pet.calls.where((m) => m.method == 'setEnabled').single.arguments, {'enabled': true});
  });

  for (final chosen in [noPetId, 'user-cat']) {
    test('a pet choice already made stays: $chosen', () async {
      final c = await container(prefs: {PetPrefsController.keys.pack: chosen});
      await c.read(accessSetupProvider.notifier).choose({AccessFeature.pet});
      await c.read(accessSetupProvider.notifier).apply(readingsWith(offPhone, overlay: true));
      expect(c.read(petPrefsProvider).packId, chosen);
      expect(await storedPack(), chosen);
    });
  }

  test('not picked: the light phone keeps its default (no pet), nothing stored', () async {
    final c = await container();
    await c.read(accessSetupProvider.notifier).choose({AccessFeature.voice});
    await c.read(accessSetupProvider.notifier).apply(readingsWith(offPhone, overlay: true));
    expect(c.read(petPrefsProvider).packId, noPetId);
    expect(c.read(petPrefsProvider).packExplicit, isFalse);
    expect(await storedPack(), isNull);
  });

  test('a removed built-in choice falls back to no pet on every device tier', () async {
    for (final tier in DeviceTier.values) {
      final c = await container(tier: tier, prefs: {PetPrefsController.keys.pack: 'whale-girl'});
      expect(c.read(petPrefsProvider).packId, noPetId);
      expect(c.read(petPrefsProvider).packExplicit, isFalse);
    }
  });
}
