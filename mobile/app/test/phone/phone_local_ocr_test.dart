import 'dart:async';

import 'package:dsh_app/state/phone_state.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

import 'harness.dart';
import 'support.dart';

Widget policyProbe() => Consumer(
  builder: (context, ref, child) {
    ref.watch(phoneProvider);
    return const Scaffold();
  },
);

FakePhoneNative ocrNative() => FakePhoneNative(policies: {...defaultPolicies(), 'localOcrEnabled': true});

void main() {
  test('OCR accepts only Boolean wire values and stays out of ordinary writes', () {
    for (final value in <Object?>[null, 0, 1, 'true', {}, []]) {
      expect(PhonePolicies.fromMap({'localOcrEnabled': value}).localOcrEnabled, isNull);
    }
    expect(PhonePolicies.fromMap({}).localOcrEnabled, isNull);
    for (final value in [true, false]) {
      final p = PhonePolicies.fromMap({'localOcrEnabled': value});
      expect(p.localOcrEnabled, value);
      expect(p.withRule('example.app', AppRule.deny).localOcrEnabled, value);
      expect(p.withConfirmMode(PhoneConfirmMode.ask).localOcrEnabled, value);
      expect(p.withUnlock(PhoneUnlock.ownApp, true).localOcrEnabled, value);
      expect(p.toWire().containsKey('localOcrEnabled'), isFalse);
      expect(p.withLocalOcrEnabled(null).localOcrEnabled, isNull);
    }
  });

  for (final accepted in [true, false]) {
    for (final readable in [true, false]) {
      testWidgets('write $accepted/read $readable preserves receipt independently', (tester) async {
        final native = ocrNative();
        await pumpPhone(tester, policyProbe(), native: native);
        expect(native.methods, ['status', 'getPolicies', 'actionLog']);
        native.calls.clear();
        native.onSetPolicies = (args) async {
          expect(args, {'localOcrEnabled': false});
          return accepted;
        };
        native.onGetPolicies = () async => readable ? {...defaultPolicies(), 'localOcrEnabled': false} : null;
        final result = containerOf(tester).read(phoneProvider.notifier).setLocalOcrEnabled(false);
        await settlePhone(tester);
        expect(await result, accepted);
        expect(phoneOf(tester).policies!.localOcrEnabled, readable ? isFalse : isNull);
        expect(native.methods, ['setPolicies', 'getPolicies']);
      });
    }
  }

  testWidgets('save waits for a new read after the write ACK', (tester) async {
    final native = ocrNative();
    await pumpPhone(tester, policyProbe(), native: native);
    expect(native.methods, ['status', 'getPolicies', 'actionLog']);
    native.calls.clear();
    final write = Completer<bool>();
    final read = Completer<Map<String, Object?>?>();
    native.onSetPolicies = (_) => write.future;
    native.onGetPolicies = () => read.future;
    var completed = false;
    final result = containerOf(tester).read(phoneProvider.notifier).setLocalOcrEnabled(false).then((value) {
      completed = true;
      return value;
    });
    await settlePhone(tester);
    expect(native.methods, ['setPolicies']);
    expect(completed, isFalse);
    write.complete(true);
    await settlePhone(tester);
    expect(native.methods, ['setPolicies', 'getPolicies']);
    expect(completed, isFalse);
    read.complete({...defaultPolicies(), 'localOcrEnabled': false});
    await settlePhone(tester);
    expect(await result, isTrue);
    expect(phoneOf(tester).policies!.localOcrEnabled, isFalse);
  });

  testWidgets('failed refresh clears only OCR knowledge', (tester) async {
    final native = ocrNative();
    await pumpPhone(tester, policyProbe(), native: native);
    final previous = phoneOf(tester).policies!;
    native.onGetPolicies = () async => null;
    final refresh = containerOf(tester).read(phoneProvider.notifier).refreshPolicies();
    await settlePhone(tester);
    await refresh;
    expect(phoneOf(tester).policies!.localOcrEnabled, isNull);
    expect(phoneOf(tester).policies!.denyPackages, previous.denyPackages);
    expect(phoneOf(tester).policies!.confirmMode, previous.confirmMode);
    expect(phoneOf(tester).policies!.unlocks, previous.unlocks);
  });

}
