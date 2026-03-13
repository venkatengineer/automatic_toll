// This is a basic Flutter widget test.
//
// To perform an interaction with a widget in your test, use the WidgetTester
// utility in the flutter_test package. For example, you can send tap and scroll
// gestures. You can also use WidgetTester to find child widgets in the widget
// tree, read text, and verify that the values of widget properties are correct.

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:location_tracker/main.dart';

void main() {
  testWidgets('Location Tracker UI test', (WidgetTester tester) async {
    // Build our app and trigger a frame.
    await tester.pumpWidget(const MyApp());

    // Verify that the title is present.
    expect(find.text('Location Tracker'), findsOneWidget);

    // Verify that the initial text is present.
    expect(find.text('Press button to get location'), findsOneWidget);

    // Verify that the button is present.
    expect(find.byType(ElevatedButton), findsOneWidget);
  });
}
