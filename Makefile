CC ?= cc
CPPFLAGS += -Iinclude
CFLAGS ?= -std=c99 -O3 -Wall -Wextra -Wpedantic
LDLIBS += -lm
MODEL_OBJECT = build/scm_model.o
FEATURE_OBJECT = build/scm_features.o
ESTIMATOR_OBJECT = build/scm_estimator.o
ASSESS_OBJECT = build/scm_assess.o
EVIDENCE_OBJECT = build/scm_evidence.o
REMAINDER_OBJECT = build/scm_remainder.o
STABLE_OBJECT = build/scm_stable.o
CERTIFICATE_OBJECT = build/scm_certificate.o
CERTIFICATE_BOX_OBJECT = build/scm_certificate_box.o
COMPACT_EVIDENCE_OBJECT = build/scm_compact_evidence.o
COMPACT_REMAINDER_OBJECT = build/scm_compact_remainder.o
COMPACT_ASSESS_OBJECT = build/scm_compact_assess.o
COMPACT_OBJECTS = $(COMPACT_EVIDENCE_OBJECT) $(COMPACT_REMAINDER_OBJECT) $(COMPACT_ASSESS_OBJECT)
SESSION_OBJECT = build/scm_session.o
SESSION_CHECKPOINT_OBJECT = build/scm_session_checkpoint.o
SESSION_OBJECTS = $(SESSION_OBJECT) $(SESSION_CHECKPOINT_OBJECT) $(ESTIMATOR_OBJECT) $(MODEL_OBJECT) $(FEATURE_OBJECT) $(ASSESS_OBJECT)
ONLINE_OBJECT = build/scm_online.o
ONLINE_CHECKPOINT_OBJECT = build/scm_online_checkpoint.o
ONLINE_OBJECTS = $(ONLINE_OBJECT) $(ONLINE_CHECKPOINT_OBJECT) $(MODEL_OBJECT)
HYPOTHESIS_OBJECT = build/scm_hypothesis.o
HYPOTHESIS_CHECKPOINT_OBJECT = build/scm_hypothesis_checkpoint.o
HYPOTHESIS_OBJECTS = $(HYPOTHESIS_OBJECT) $(HYPOTHESIS_CHECKPOINT_OBJECT) $(MODEL_OBJECT)
TEST_NAMES = $(basename $(notdir $(wildcard tests/test_*.c)))
TEST_BINS = $(addprefix build/,$(TEST_NAMES))
.PHONY: all test test-assess test-evidence test-remainder test-stable test-certificate test-certificate-box test-compact test-session test-online test-hypothesis hypothesis-stack online-stack session-stack compact-stack evidence-stack remainder-stack sanitize clean
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
build/test_remainder: tests/test_remainder.c $(REMAINDER_OBJECT) $(EVIDENCE_OBJECT) $(MODEL_OBJECT) | build
	$(CC) $(CPPFLAGS) $(CFLAGS) $(LDFLAGS) $^ $(LDLIBS) -o $@
build/scm_remainder_probe: tools/remainder_probe.c $(REMAINDER_OBJECT) $(EVIDENCE_OBJECT) $(MODEL_OBJECT) $(ASSESS_OBJECT) | build
	$(CC) $(CPPFLAGS) $(CFLAGS) $(LDFLAGS) $^ $(LDLIBS) -o $@
test-evidence: build/test_evidence
	./build/test_evidence
test-remainder: build/test_remainder
	./build/test_remainder
build/test_compact: tests/test_compact.c tools/compact_compare.h $(COMPACT_OBJECTS) $(REMAINDER_OBJECT) $(EVIDENCE_OBJECT) $(MODEL_OBJECT) $(ASSESS_OBJECT) | build
	$(CC) $(CPPFLAGS) $(CFLAGS) $(LDFLAGS) $(filter-out %.h,$^) $(LDLIBS) -o $@
build/test_compact_assess: tests/test_compact_assess.c $(COMPACT_ASSESS_OBJECT) $(COMPACT_EVIDENCE_OBJECT) $(EVIDENCE_OBJECT) $(MODEL_OBJECT) $(ASSESS_OBJECT) | build
	$(CC) $(CPPFLAGS) $(CFLAGS) $(LDFLAGS) $^ $(LDLIBS) -o $@
build/scm_compact_probe: tools/compact_probe.c tools/compact_compare.h $(COMPACT_OBJECTS) $(REMAINDER_OBJECT) $(EVIDENCE_OBJECT) $(MODEL_OBJECT) $(ASSESS_OBJECT) | build
	$(CC) $(CPPFLAGS) $(CFLAGS) $(LDFLAGS) $(filter-out %.h,$^) $(LDLIBS) -o $@
test-compact: build/test_compact build/test_compact_assess
	./build/test_compact
	./build/test_compact_assess
build/test_session: tests/test_session.c $(SESSION_OBJECT) $(ESTIMATOR_OBJECT) $(MODEL_OBJECT) $(FEATURE_OBJECT) $(ASSESS_OBJECT) | build
	$(CC) $(CPPFLAGS) $(CFLAGS) $(LDFLAGS) $^ $(LDLIBS) -o $@
build/test_session_checkpoint: tests/test_session_checkpoint.c $(SESSION_OBJECTS) | build
	$(CC) $(CPPFLAGS) $(CFLAGS) $(LDFLAGS) $^ $(LDLIBS) -o $@
build/scm_session_probe: tools/session_probe.c $(SESSION_OBJECTS) | build
	$(CC) $(CPPFLAGS) $(CFLAGS) $(LDFLAGS) $^ $(LDLIBS) -o $@
test-session: build/test_session build/test_session_checkpoint
	./build/test_session
	./build/test_session_checkpoint
build/test_online: tests/test_online.c $(ONLINE_OBJECT) $(MODEL_OBJECT) | build
	$(CC) $(CPPFLAGS) $(CFLAGS) $(LDFLAGS) $^ $(LDLIBS) -o $@
build/test_online_checkpoint: tests/test_online_checkpoint.c $(ONLINE_OBJECTS) | build
	$(CC) $(CPPFLAGS) $(CFLAGS) $(LDFLAGS) $^ $(LDLIBS) -o $@
build/scm_online_probe: tools/online_probe.c $(ONLINE_OBJECTS) | build
	$(CC) $(CPPFLAGS) $(CFLAGS) $(LDFLAGS) $^ $(LDLIBS) -o $@
test-online: build/test_online build/test_online_checkpoint
	./build/test_online
	./build/test_online_checkpoint
build/scm_hypothesis_checkpoint.o: src/scm_hypothesis_checkpoint.c | build
	$(CC) $(CPPFLAGS) $(CFLAGS) -MMD -MP -c $< -o $@
build/test_hypothesis: tests/test_hypothesis.c $(HYPOTHESIS_OBJECT) $(ONLINE_OBJECT) $(MODEL_OBJECT) | build
	$(CC) $(CPPFLAGS) $(CFLAGS) $(LDFLAGS) $^ $(LDLIBS) -o $@
build/test_hypothesis_checkpoint: tests/test_hypothesis_checkpoint.c $(HYPOTHESIS_OBJECTS) | build
	$(CC) $(CPPFLAGS) $(CFLAGS) $(LDFLAGS) $^ $(LDLIBS) -o $@
build/scm_hypothesis_probe: tools/hypothesis_probe.c $(HYPOTHESIS_OBJECTS) | build
	$(CC) $(CPPFLAGS) $(CFLAGS) $(LDFLAGS) $^ $(LDLIBS) -o $@
test-hypothesis: build/test_hypothesis build/test_hypothesis_checkpoint
	./build/test_hypothesis
	./build/test_hypothesis_checkpoint
# New candidate only; own-source host frames do not qualify target runtime.
hypothesis-stack: | build
	mkdir -p build/hypothesis-stack
	$(CC) $(CPPFLAGS) $(CFLAGS) -fstack-usage -c src/scm_hypothesis.c -o build/hypothesis-stack/scm_hypothesis.o
	$(CC) $(CPPFLAGS) $(CFLAGS) -DSCM_HYPOTHESIS_NO_HOST_IO -fstack-usage -c src/scm_hypothesis_checkpoint.c -o build/hypothesis-stack/scm_hypothesis_checkpoint_core.o
	$(CC) $(CPPFLAGS) $(CFLAGS) -fstack-usage -c src/scm_hypothesis_checkpoint.c -o build/hypothesis-stack/scm_hypothesis_checkpoint_host.o
	$(CC) $(CPPFLAGS) $(CFLAGS) -fstack-usage -c tools/hypothesis_probe.c -o build/hypothesis-stack/hypothesis_probe.o
	$(CC) $(CPPFLAGS) $(CFLAGS) -fstack-usage -c src/scm_model.c -o build/hypothesis-stack/scm_model.o
online-stack: | build
	mkdir -p build/online-stack
	$(CC) $(CPPFLAGS) $(CFLAGS) -fstack-usage -c src/scm_online.c -o build/online-stack/scm_online.o
	$(CC) $(CPPFLAGS) $(CFLAGS) -fstack-usage -c src/scm_online_checkpoint.c -o build/online-stack/scm_online_checkpoint.o
	$(CC) $(CPPFLAGS) $(CFLAGS) -fstack-usage -c tools/online_probe.c -o build/online-stack/online_probe.o
# M1 is a desktop retained-history adapter; these host frames are not a target
# SRAM bound and exclude library/runtime/caller costs and dynamic allocations.
session-stack: | build
	mkdir -p build/session-stack
	$(CC) $(CPPFLAGS) $(CFLAGS) -fstack-usage -c src/scm_session.c -o build/session-stack/scm_session.o
	$(CC) $(CPPFLAGS) $(CFLAGS) -fstack-usage -c src/scm_session_checkpoint.c -o build/session-stack/scm_session_checkpoint.o
	$(CC) $(CPPFLAGS) $(CFLAGS) -fstack-usage -c tools/session_probe.c -o build/session-stack/session_probe.o
# Own-source host stack only. Library, caller, IRQ and target stack are extra.
compact-stack: | build
	mkdir -p build/compact-stack
	$(CC) $(CPPFLAGS) $(CFLAGS) -fstack-usage -c src/scm_compact_evidence.c -o build/compact-stack/scm_compact_evidence.o
	$(CC) $(CPPFLAGS) $(CFLAGS) -fstack-usage -c src/scm_compact_remainder.c -o build/compact-stack/scm_compact_remainder.o
	$(CC) $(CPPFLAGS) $(CFLAGS) -fstack-usage -c src/scm_compact_assess.c -o build/compact-stack/scm_compact_assess.o
	$(CC) $(CPPFLAGS) $(CFLAGS) -fstack-usage -c src/scm_evidence.c -o build/compact-stack/scm_evidence.o
	$(CC) $(CPPFLAGS) $(CFLAGS) -fstack-usage -c src/scm_model.c -o build/compact-stack/scm_model.o
	$(CC) $(CPPFLAGS) $(CFLAGS) -fstack-usage -c src/scm_assess.c -o build/compact-stack/scm_assess.o
	$(CC) $(CPPFLAGS) $(CFLAGS) -fstack-usage -c tools/compact_probe.c -o build/compact-stack/compact_probe.o
build/test_stable: tests/test_stable.c $(STABLE_OBJECT) | build
	$(CC) $(CPPFLAGS) $(CFLAGS) $(LDFLAGS) $^ -o $@
test-stable: build/test_stable
	./build/test_stable
build/test_certificate: tests/test_certificate.c $(CERTIFICATE_OBJECT) $(STABLE_OBJECT) | build
	$(CC) $(CPPFLAGS) $(CFLAGS) $(LDFLAGS) $^ -o $@
test-certificate: build/test_certificate
	./build/test_certificate
build/test_certificate_box: tests/test_certificate_box.c $(CERTIFICATE_BOX_OBJECT) $(CERTIFICATE_OBJECT) $(STABLE_OBJECT) | build
	$(CC) $(CPPFLAGS) $(CFLAGS) $(LDFLAGS) $^ -o $@
test-certificate-box: build/test_certificate_box
	./build/test_certificate_box
# Separate objects preserve the reference executable. These reports describe
# this host/compiler; library stack and Cortex-M23 stack remain unmeasured.
evidence-stack: | build
	mkdir -p build/evidence-stack
	$(CC) $(CPPFLAGS) $(CFLAGS) -fstack-usage -c src/scm_evidence.c -o build/evidence-stack/scm_evidence.o
	$(CC) $(CPPFLAGS) $(CFLAGS) -fstack-usage -c src/scm_model.c -o build/evidence-stack/scm_model.o
	$(CC) $(CPPFLAGS) $(CFLAGS) -fstack-usage -c src/scm_assess.c -o build/evidence-stack/scm_assess.o
	$(CC) $(CPPFLAGS) $(CFLAGS) -fstack-usage -c tools/evidence_probe.c -o build/evidence-stack/evidence_probe.o
# Independent host stack report; does not overwrite the frozen B001 reports.
remainder-stack: | build
	mkdir -p build/remainder-stack
	$(CC) $(CPPFLAGS) $(CFLAGS) -fstack-usage -c src/scm_remainder.c -o build/remainder-stack/scm_remainder.o
	$(CC) $(CPPFLAGS) $(CFLAGS) -fstack-usage -c src/scm_evidence.c -o build/remainder-stack/scm_evidence.o
	$(CC) $(CPPFLAGS) $(CFLAGS) -fstack-usage -c src/scm_model.c -o build/remainder-stack/scm_model.o
	$(CC) $(CPPFLAGS) $(CFLAGS) -fstack-usage -c src/scm_assess.c -o build/remainder-stack/scm_assess.o
	$(CC) $(CPPFLAGS) $(CFLAGS) -fstack-usage -c tools/remainder_probe.c -o build/remainder-stack/remainder_probe.o
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
	  $(CC) $(CPPFLAGS) -std=c99 -O1 -g -Wall -Wextra -Wpedantic -fsanitize=address,undefined -fno-omit-frame-pointer src/scm_model.c src/scm_features.c src/scm_estimator.c src/scm_assess.c src/scm_evidence.c src/scm_remainder.c src/scm_stable.c src/scm_certificate.c src/scm_certificate_box.c src/scm_compact_evidence.c src/scm_compact_remainder.c src/scm_compact_assess.c src/scm_session.c src/scm_session_checkpoint.c src/scm_online.c src/scm_online_checkpoint.c src/scm_hypothesis.c src/scm_hypothesis_checkpoint.c tests/$$name.c $(LDLIBS) -o build/$${name}_sanitized; \
	  ASAN_OPTIONS=detect_leaks=0 ./build/$${name}_sanitized; \
	done
clean:
	rm -rf build
-include build/*.d
