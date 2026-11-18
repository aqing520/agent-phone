// 设置 → 手机操控 → 悬浮条 (lib/ui/phone/phone_control_screen.dart): 闲置时不透明度
// (30–100 %, 70 % by default, sent to the native side on every step so a showing
// pill follows), 闲置时自动收起 (off by default) and 完成后返回 DSH Go, shown
// once phone control is on.


import 'package:dsh_app/phone/phone_channel.dart';
import 'package:flutter_test/flutter_test.dart';


void main() {
  group('model', () {
    test('opacity stays within 30–100 % on whole percents', () {
      expect(PhoneOverlayPrefs.clampOpacity(0.1), 0.3);
      expect(PhoneOverlayPrefs.clampOpacity(1.3), 1.0);
      expect(PhoneOverlayPrefs.clampOpacity(0.6666), 0.67);
      expect(PhoneOverlayPrefs.fromMap(const {}).idleOpacity, 0.7);
      // 闲置时自动收起 is on unless the native side says it was turned off.
      expect(PhoneOverlayPrefs.fromMap(const {}).autoCollapse, isTrue);
      expect(const PhoneOverlayPrefs().autoCollapse, isTrue);
      expect(PhoneOverlayPrefs.fromMap(const {'autoCollapse': false}).autoCollapse, isFalse);
      expect(PhoneOverlayPrefs.fromMap(const {'idleOpacity': 0.5, 'autoCollapse': true}).percent, 50);
    });
  });

}
