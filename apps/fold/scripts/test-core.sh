#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p .build/core-tests
"${CC:-cc}" -std=c11 -O1 -g -Wall -Wextra -Werror -pedantic \
  -fsanitize=address,undefined -fno-omit-frame-pointer \
  -I Sources/FoldCore/include Sources/FoldCore/FoldCore.c Tests/core_tests.c \
  -lm -o .build/core-tests/check
.build/core-tests/check
