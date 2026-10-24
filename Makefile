CC ?= cc
CPPFLAGS += -Iinclude
CFLAGS ?= -std=c99 -O3 -Wall -Wextra -Wpedantic
LDLIBS += -lm
MODEL_OBJECT = build/scm_model.o
FEATURE_OBJECT = build/scm_features.o
ESTIMATOR_OBJECT = build/scm_estimator.o
ASSESS_OBJECT = build/scm_assess.o
TEST_NAMES = $(basename $(notdir $(wildcard tests/test_*.c)))
TEST_BINS = $(addprefix build/,$(TEST_NAMES))
.PHONY: all test test-assess sanitize clean
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
	  $(CC) $(CPPFLAGS) -std=c99 -O1 -g -Wall -Wextra -Wpedantic -fsanitize=address,undefined -fno-omit-frame-pointer src/scm_model.c src/scm_features.c src/scm_estimator.c src/scm_assess.c tests/$$name.c $(LDLIBS) -o build/$${name}_sanitized; \
	  ASAN_OPTIONS=detect_leaks=0 ./build/$${name}_sanitized; \
	done
clean:
	rm -rf build
-include build/*.d
