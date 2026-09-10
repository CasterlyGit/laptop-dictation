#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
if [[ "$(uname -s)" != Darwin ]]; then
  echo 'Fold is a macOS app. Build it on macOS 14+ with Xcode Command Line Tools.' >&2
  exit 1
fi
if ! xcrun --find swift >/dev/null 2>&1; then
  echo 'Install the free Xcode Command Line Tools with xcode-select --install, then run this again.' >&2
  exit 1
fi
build_args=(-c release)
if [[ "${FOLD_UNIVERSAL:-0}" == 1 ]]; then build_args+=(--arch arm64 --arch x86_64); fi
swift build "${build_args[@]}"
binary_dir="$(swift build "${build_args[@]}" --show-bin-path)"
app_dir="$PWD/dist/Fold.app"
mkdir -p "$app_dir/Contents/MacOS" "$app_dir/Contents/Resources"
cp "$binary_dir/Fold" "$app_dir/Contents/MacOS/Fold"
for bundle in "$binary_dir"/*.bundle; do
  [[ -d "$bundle" ]] && ditto "$bundle" "$app_dir/Contents/Resources/$(basename "$bundle")"
done
cp packaging/Info.plist "$app_dir/Contents/Info.plist"
if [[ "${FOLD_VALIDATE_METAL:-0}" == 1 ]]; then
  xcrun -sdk macosx metal -c Sources/Fold/Resources/Fold.metal -o .build/Fold.air
fi
codesign --force --deep --sign - "$app_dir"
codesign --verify --deep --strict "$app_dir"
echo "Built $app_dir"
