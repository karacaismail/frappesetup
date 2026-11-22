set -eu
fixture=$(mktemp -d /tmp/gitleaks-fixture.XXXXXX)
git init --quiet "$fixture"
cd "$fixture"
printf 'api_key = "%s%s"\n' r7Qn8aNM4wYX f0K9MtG6pL2vbRc5 > sample.txt
git add sample.txt
fixture_name=karacaismail
fixture_email=35493655+karacaismail@users.noreply.github.com
GIT_AUTHOR_NAME="$fixture_name" GIT_AUTHOR_EMAIL="$fixture_email" \
    GIT_COMMITTER_NAME="$fixture_name" GIT_COMMITTER_EMAIL="$fixture_email" \
    git commit --quiet -m 'Synthetic scanner fixture'
test "$(git log -1 --format='%an <%ae> %cn <%ce>')" = \
    "$fixture_name <$fixture_email> $fixture_name <$fixture_email>"
exit_code=0
gitleaks git --no-banner --redact=100 --report-path "$fixture/findings.json" "$fixture" || exit_code=$?
test "$exit_code" -eq 1 && grep -q '"RuleID": "generic-api-key"' "$fixture/findings.json"
