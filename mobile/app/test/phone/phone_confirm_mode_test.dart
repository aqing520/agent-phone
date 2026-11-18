import 'package:dsh_app/phone/phone_channel.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  test('wire: unknown or missing modes read as 每次都询问', () {
    expect(PhonePolicies.fromMap({}).confirmMode, PhoneConfirmMode.ask);
    expect(PhonePolicies.fromMap({'confirmMode': 'yolo'}).confirmMode, PhoneConfirmMode.ask);
    expect(PhonePolicies.fromMap({'confirmMode': 'task'}).confirmMode, PhoneConfirmMode.task);
    final p = PhonePolicies.fromMap({
      'denyPackages': ['a.b'],
      'confirmMode': 'always',
    });
    expect(p.withRule('c.d', AppRule.deny).confirmMode, PhoneConfirmMode.always);
    expect(p.toWire()['confirmMode'], 'always');
    expect(PhoneDecision.parse('confirmed-task'), PhoneDecision.allowed);
  });
}
