import 'package:flutter_test/flutter_test.dart';
import 'package:interactive_video_lessons/main.dart';

void main() {
  testWidgets('Smoke test', (WidgetTester tester) async {
    await tester.pumpWidget(const MyApp());
    expect(find.text('Interactive Video Lessons'), findsOneWidget);
  });
}
