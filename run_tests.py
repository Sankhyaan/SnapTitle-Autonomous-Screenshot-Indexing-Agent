"""SnapTitle Automated Test Suite Runner.

Discovers and runs all project test suites sequentially with formatted summary output.
"""

import sys
import time
import unittest
from pathlib import Path

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


TEST_MODULES = [
    ("Environment & Models", "tests.test_env"),
    ("Detection & Renaming", "tests.test_detection_and_renaming"),
    ("OCR + LLM Titling", "tests.test_ocr_llm_titling"),
    ("VLM Fallback", "tests.test_vlm_fallback"),
    ("Popup UI & Notifications", "tests.test_popup_ui"),
    ("Duplicate Resolution", "tests.test_smart_duplicate_resolution"),
    ("SQLite Database & Search", "tests.test_search_and_database"),
]


def run_all_tests():
    print("=" * 70)
    print("           SnapTitle - Complete Test Suite Runner           ")
    print("=" * 70)

    loader = unittest.TestLoader()
    results = []
    total_start = time.time()

    for name, module_path in TEST_MODULES:
        print(f"\n[RUNNING] {name} ({module_path})...")
        t0 = time.time()
        try:
            suite = loader.loadTestsFromName(module_path)
            runner = unittest.TextTestRunner(verbosity=1)
            result = runner.run(suite)
            elapsed = time.time() - t0
            passed = result.wasSuccessful()
            results.append((name, result.testsRun, len(result.errors), len(result.failures), elapsed, passed))
        except Exception as e:
            elapsed = time.time() - t0
            results.append((name, 0, 1, 0, elapsed, False))
            print(f"Error loading {module_path}: {e}")

    total_elapsed = time.time() - total_start

    print("\n" + "=" * 70)
    print("                       TEST EXECUTION SUMMARY                       ")
    print("=" * 70)
    print(f"{'Test Module':<28} {'Tests':<8} {'Errors':<8} {'Failures':<10} {'Time':<8} {'Status'}")
    print("-" * 70)

    all_passed = True
    for name, count, errors, failures, duration, passed in results:
        status_str = "[PASSED]" if passed else "[FAILED]"
        if not passed:
            all_passed = False
        print(f"{name:<28} {count:<8} {errors:<8} {failures:<10} {duration:.2f}s   {status_str}")

    print("=" * 70)
    print(f"Total Execution Time: {total_elapsed:.2f}s")
    if all_passed:
        print(">> ALL TEST SUITES PASSED SUCCESSFULLY! <<")
    else:
        print(">> SOME TESTS FAILED! <<")
    print("=" * 70)

    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(run_all_tests())
