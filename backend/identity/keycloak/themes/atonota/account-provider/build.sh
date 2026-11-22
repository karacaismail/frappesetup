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

mkdir -p "$out/classes" "$out/check-classes"
main_sources=()
while IFS= read -r file; do main_sources+=("$file"); done < <(find "$src/main/java" -name '*.java' | sort)
check_sources=()
while IFS= read -r file; do check_sources+=("$file"); done < <(find "$src/test/java" -name '*.java' | sort)

javac --release 21 -Xlint:all -Werror -proc:none -cp "$classpath" -d "$out/classes" "${main_sources[@]}"
cp -r "$src/main/resources/META-INF" "$out/classes/META-INF"
jar --create --file "$out/account-deletion-link-provider.jar" -C "$out/classes" .

# The checks run with assertions on. A failed check stops the build. The check classes stay out of the jar.
javac --release 21 -Xlint:all -Werror -proc:none -cp "$out/classes:$classpath" -d "$out/check-classes" "${check_sources[@]}"
java -ea -cp "$out/check-classes:$out/classes:$classpath" platform.identity.account.AccountDeletionLinkConsoleCheck
