CC ?= cc
CPPFLAGS += -Iinclude
CFLAGS ?= -std=c99 -O3 -Wall -Wextra -Wpedantic
LDLIBS += -lm
MODEL_OBJECT = build/scm_model.o
FEATURE_OBJECT = build/scm_features.o
ESTIMATOR_OBJECT = build/scm_estimator.o
ASSESS_OBJECT = build/scm_assess.o
EVIDENCE_OBJECT = build/scm_evidence.o
TEST_NAMES = $(basename $(notdir $(wildcard tests/test_*.c)))
TEST_BINS = $(addprefix build/,$(TEST_NAMES))
.PHONY: all test test-assess test-evidence evidence-stack sanitize clean
all: build/scm_estimator
build:
	mkdir -p build
build/%.o: src/%.c | build
	$(CC) $(CPPFLAGS) $(CFLAGS) -MMD -MP -c $< -o $@
build/scm_estimator: build/main.o $(ESTIMATOR_OBJECT) $(MODEL_OBJECT) $(FEATURE_OBJECT) $(ASSESS_OBJECT)
	$(CC) $(CFLAGS) $(LDFLAGS) $^ $(LDLIBS) -o $@
build/test_features: tests/test_features.c $(FEATURE_OBJECT) | build
	$(CC) $(CPPFLAGS) $(CFLAGS) $(LDFLAGS) $^ $(LDLIBS) -o $@
build/test_model: tests/test_model.c $(MODEL_OBJECT) | build
	$(CC) $(CPPFLAGS) $(CFLAGS) $(LDFLAGS) $^ $(LDLIBS) -o $@
build/test_canaries: tests/test_canaries.c $(MODEL_OBJECT) | build
	$(CC) $(CPPFLAGS) $(CFLAGS) $(LDFLAGS) $^ $(LDLIBS) -o $@
build/test_assess_c: tests/test_assess_c.c $(ASSESS_OBJECT) | build
	$(CC) $(CPPFLAGS) $(CFLAGS) $(LDFLAGS) $^ $(LDLIBS) -o $@
build/test_evidence: tests/test_evidence.c $(EVIDENCE_OBJECT) $(MODEL_OBJECT) | build
	$(CC) $(CPPFLAGS) $(CFLAGS) $(LDFLAGS) $^ $(LDLIBS) -o $@
build/scm_evidence_probe: tools/evidence_probe.c $(EVIDENCE_OBJECT) $(MODEL_OBJECT) $(ASSESS_OBJECT) | build
	$(CC) $(CPPFLAGS) $(CFLAGS) $(LDFLAGS) $^ $(LDLIBS) -o $@
test-evidence: build/test_evidence
	./build/test_evidence
# Separate objects preserve the reference executable. These reports describe
# this host/compiler; library stack and Cortex-M23 stack remain unmeasured.
evidence-stack: | build
	mkdir -p build/evidence-stack
	$(CC) $(CPPFLAGS) $(CFLAGS) -fstack-usage -c src/scm_evidence.c -o build/evidence-stack/scm_evidence.o
	$(CC) $(CPPFLAGS) $(CFLAGS) -fstack-usage -c src/scm_model.c -o build/evidence-stack/scm_model.o
	$(CC) $(CPPFLAGS) $(CFLAGS) -fstack-usage -c src/scm_assess.c -o build/evidence-stack/scm_assess.o
	$(CC) $(CPPFLAGS) $(CFLAGS) -fstack-usage -c tools/evidence_probe.c -o build/evidence-stack/evidence_probe.o
build/test_%: tests/test_%.c $(ESTIMATOR_OBJECT) $(MODEL_OBJECT) $(FEATURE_OBJECT) | build
	$(CC) $(CPPFLAGS) $(CFLAGS) $(LDFLAGS) $^ $(LDLIBS) -o $@
test: $(TEST_BINS)
	@set -e; for test in $(TEST_BINS); do ./$$test; done
ifneq ($(wildcard tests/test_assess.py),)
test: test-assess
test-assess:
	python3 tests/test_assess.py
endif
# Leak detection needs /proc access unavailable on some hosted executors.
# This checks address/undefined behavior only; it is not a leak audit.
sanitize: | build
	@set -e; for name in $(TEST_NAMES); do \
	  $(CC) $(CPPFLAGS) -std=c99 -O1 -g -Wall -Wextra -Wpedantic -fsanitize=address,undefined -fno-omit-frame-pointer src/scm_model.c src/scm_features.c src/scm_estimator.c src/scm_assess.c src/scm_evidence.c tests/$$name.c $(LDLIBS) -o build/$${name}_sanitized; \
	  ASAN_OPTIONS=detect_leaks=0 ./build/$${name}_sanitized; \
	done
clean:
	rm -rf build
-include build/*.d
