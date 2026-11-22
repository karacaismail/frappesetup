#!/usr/bin/env bash
# Builds the account console provider. This is the only place that compiles it.
# Every image that needs the provider calls this script. A test fails when another file repeats the step.
#
# Usage: build.sh <keycloak-lib-dir> <source-dir> <output-dir>
#   <keycloak-lib-dir>  /opt/keycloak/lib/lib of the Keycloak image (holds "main" and "boot")
#   <source-dir>        the "src" folder next to this script
#   <output-dir>        receives account-deletion-link-provider.jar
# Needs a JDK 21 (javac, jar, java). No build tool and no extra dependency.
set -euo pipefail

if [[ $# -ne 3 ]]; then
  echo "Usage: build.sh <keycloak-lib-dir> <source-dir> <output-dir>" >&2
  exit 2
fi
lib="$1"
src="$2"
out="$3"
classpath="$lib/main/*:$lib/boot/*"

mkdir -p -- "$out"
out="$(cd -- "$out" && pwd -P)"
# Build in fresh directories so a repeat build cannot package old classes or metadata.
build_dir="$(mktemp -d "$out/.provider-build.XXXXXX")"
trap 'rm -rf -- "$build_dir"' EXIT
mkdir -p "$build_dir/classes" "$build_dir/check-classes"
main_sources=()
while IFS= read -r file; do main_sources+=("$file"); done < <(find "$src/main/java" -name '*.java' | sort)
check_sources=()
while IFS= read -r file; do check_sources+=("$file"); done < <(find "$src/test/java" -name '*.java' | sort)

javac --release 21 -Xlint:all -Werror -proc:none -cp "$classpath" -d "$build_dir/classes" "${main_sources[@]}"
cp -r "$src/main/resources/META-INF" "$build_dir/classes/META-INF"
jar --create --file "$build_dir/account-deletion-link-provider.jar" -C "$build_dir/classes" .

# The checks run with assertions on. A failed check stops the build. The check classes stay out of the jar.
javac --release 21 -Xlint:all -Werror -proc:none -cp "$build_dir/classes:$classpath" -d "$build_dir/check-classes" "${check_sources[@]}"
java -ea -cp "$build_dir/check-classes:$build_dir/classes:$classpath" platform.identity.account.AccountDeletionLinkConsoleCheck
mv -f -- "$build_dir/account-deletion-link-provider.jar" "$out/"
