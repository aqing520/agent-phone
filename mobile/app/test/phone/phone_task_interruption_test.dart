
import 'package:dsh_app/phone/phone_channel.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

const batch = '00000000-0000-4000-8000-000000000001';
Map<String, Object?> interruption({String state = 'ready', int count = 1}) => {
  'version': 1, 'state': state, 'count': count,
  'batchToken': state == 'ready' && count > 0 ? batch : null,
  'error': state == 'error' ? 'writeFailed' : null,
};

void main() {
  setUp(() => SharedPreferences.setMockInitialValues({}));

  test('old native and malformed summaries never invent an acknowledgement token or task', () {
    expect(PhoneStatus.fromMap({}).taskInterruption.visible, isFalse);
    for (final value in [
      {'version': 2},
      {...interruption(), 'count': 1.0},
      {...interruption(), 'batchToken': 'wrong'},
      {...interruption(), 'error': 'loadFailed'},
      {...interruption(state: 'error'), 'batchToken': batch},
    ]) {
      final status = PhoneStatus.fromMap({'taskInterruption': value});
      expect(status.taskInterruption.canAcknowledge, isFalse);
      expect(status.tasks, isEmpty); expect(status.task.active, isFalse);
    }
    final status = PhoneStatus.fromMap({'taskInterruption': interruption()});
    expect(status.taskInterruption.canAcknowledge, isTrue);
    expect(status.copyWith(enabled: true).taskInterruption.batchToken, batch);
    expect(status.tasks, isEmpty);
  });

}
