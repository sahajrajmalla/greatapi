#!/usr/bin/env bash
#
# Production-readiness QA.
#
# Builds the wheel, installs it into a clean virtualenv, and puts the whole
# thing through the journey a real user takes -- scaffold, migrate, boot, sign
# in, click every page -- asserting security and packaging properties as it
# goes. Runs against the *installed* package in production mode, which is what
# the unit tests, running from the source tree with debug on, cannot check.
#
#   make qa
#
# Requires: python3, curl. Uses `uv` when available, `python -m venv` otherwise.
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORK="$(mktemp -d)"

# The project venv has the build backend; the system interpreter may not.
if [ -x "$REPO/.venv/bin/python" ]; then
  PY="$REPO/.venv/bin/python"
else
  PY="$(command -v python3)"
fi
PORT="${QA_PORT:-8321}"
FAIL=0

pass() { printf "  \033[32mPASS\033[0m %s\n" "$1"; }
fail() { printf "  \033[31mFAIL\033[0m %s\n" "$1"; FAIL=1; }
check() { if [ "$2" = "$3" ]; then pass "$1 ($3)"; else fail "$1 (expected $3, got $2)"; fi; }

cleanup() {
  if [ -n "${SERVER_PID:-}" ]; then
    kill "$SERVER_PID" 2>/dev/null || true
    wait "$SERVER_PID" 2>/dev/null || true
  fi
  rm -rf "$WORK"
}
trap cleanup EXIT

echo "== 1. build and install the wheel into a clean venv =="
cd "$REPO"
if [ -z "${QA_SKIP_BUILD:-}" ]; then
  rm -rf dist
  "$PY" -m build --wheel --outdir dist >/dev/null 2>&1 || {
    echo "  could not build a wheel. Run 'make install' first, or: pip install build"
    exit 1
  }
fi
WHEEL="$(ls "$REPO"/dist/*.whl | head -1)"

if command -v uv >/dev/null 2>&1; then
  uv venv "$WORK/venv" >/dev/null 2>&1
  uv pip install --python "$WORK/venv/bin/python" -q "${WHEEL}[ai]" >/dev/null 2>&1
else
  "$PY" -m venv "$WORK/venv"
  "$WORK/venv/bin/python" -m pip install -q --upgrade pip
  "$WORK/venv/bin/python" -m pip install -q "${WHEEL}[ai]"
fi
BIN="$WORK/venv/bin"

VERSION="$("$PY" -c "import re,pathlib;print(re.search(r'__version__ = \"([^\"]+)\"', pathlib.Path('$REPO/src/greatapi/__init__.py').read_text()).group(1))")"
check "greatapi --version" "$("$BIN/greatapi" --version)" "greatapi $VERSION"

echo
echo "== 2. scaffold, migrate, create an admin =="
cd "$WORK"
"$BIN/greatapi" startproject shop >/dev/null
cd shop
export GREATAPI_SECRET_KEY="$("$BIN/greatapi" generate-secret)"
export GREATAPI_DEBUG=false          # production mode, deliberately
export GREATAPI_DATABASE_URL="sqlite+aiosqlite:///$PWD/app.db"

"$BIN/greatapi" startapp catalog >/dev/null
"$BIN/greatapi" makemigrations -m initial >/dev/null 2>&1
"$BIN/greatapi" migrate >/dev/null 2>&1
"$BIN/greatapi" createsuperuser --noinput --email qa@example.com --username qa \
  --password "hunter2hunter2" >/dev/null
pass "startproject -> startapp -> makemigrations -> migrate -> createsuperuser"

echo
echo "== 3. a missing secret key must stop the app in production mode =="
# Captured rather than piped: with `pipefail` the pipeline would inherit the
# CLI's non-zero exit and read as a failure even when the grep matched.
set +e
NOKEY_OUT=$(unset GREATAPI_SECRET_KEY; "$BIN/greatapi" routes 2>&1); NOKEY_RC=$?
set -e
grep -q "generate-secret" <<<"$NOKEY_OUT" \
  && pass "refuses to start without a secret key, and says how to make one" \
  || fail "no actionable message: $NOKEY_OUT"
check "exit code is non-zero, so a container restarts" "$([ $NOKEY_RC -ne 0 ] && echo nonzero)" "nonzero"

echo
echo "== 4. boot in production mode =="
"$BIN/greatapi" runserver --no-reload --port $PORT >server.log 2>&1 &
SERVER_PID=$!
for _ in $(seq 1 40); do curl -sf "http://127.0.0.1:$PORT/health" >/dev/null 2>&1 && break; sleep 0.5; done
check "GET /health" "$(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:$PORT/health)" "200"

echo
echo "== 5. anonymous access is refused =="
check "GET /admin (browser)" \
  "$(curl -s -o /dev/null -w '%{http_code}' -H 'accept: text/html' http://127.0.0.1:$PORT/admin)" "303"
check "GET user list (api)" \
  "$(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:$PORT/admin/model/auth/greatapi_user)" "401"
check "GET usage" \
  "$(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:$PORT/admin/usage)" "401"

echo
echo "== 6. security headers =="
HEAD=$(curl -sI -H 'accept: text/html' http://127.0.0.1:$PORT/admin/login)
grep -qi "x-content-type-options: nosniff" <<<"$HEAD" && pass "X-Content-Type-Options" || fail "X-Content-Type-Options"
grep -qi "x-frame-options: DENY" <<<"$HEAD" && pass "X-Frame-Options" || fail "X-Frame-Options"
grep -qi "content-security-policy" <<<"$HEAD" && pass "Content-Security-Policy" || fail "CSP"
grep -qi "unsafe-inline" <<<"$HEAD" && fail "CSP contains unsafe-inline" || pass "CSP has no unsafe-inline"

echo
echo "== 7. sign in =="
JAR="$WORK/jar"
curl -s -c "$JAR" -o /dev/null http://127.0.0.1:$PORT/admin/login
LOGIN=$(curl -s -b "$JAR" -c "$JAR" -o /dev/null -w '%{http_code}' \
  -d 'username=qa&password=hunter2hunter2' http://127.0.0.1:$PORT/admin/login)
check "POST /admin/login" "$LOGIN" "303"
grep -q "^#HttpOnly_" "$JAR" && pass "session cookie is HttpOnly" || fail "session cookie is not HttpOnly"

echo
echo "== 8. wrong credentials are indistinguishable =="
A=$(curl -s -o /dev/null -w '%{http_code}' -d 'username=nobody&password=whatever12' http://127.0.0.1:$PORT/admin/login)
B=$(curl -s -o /dev/null -w '%{http_code}' -d 'username=qa&password=wrongpass1' http://127.0.0.1:$PORT/admin/login)
[ "$A" = "$B" ] && pass "unknown user and wrong password both $A" || fail "differ: $A vs $B"

echo
echo "== 9. every admin page renders =="
for path in /admin /admin/account /admin/usage /admin/jobs /admin/api-keys \
            /admin/model/auth/greatapi_user /admin/model/catalog/catalog_item \
            /admin/model/system/greatapi_job /admin/model/ai/greatapi_llm_call; do
  check "GET $path" "$(curl -s -b "$JAR" -o /dev/null -w '%{http_code}' "http://127.0.0.1:$PORT$path")" "200"
done

echo
echo "== 10. no credential ever reaches the browser =="
LEAK=0
for path in /admin /admin/account /admin/model/auth/greatapi_user; do
  curl -s -b "$JAR" "http://127.0.0.1:$PORT$path" | grep -qE '\$2[aby]?\$|\$argon2' && LEAK=1
done
[ "$LEAK" = 0 ] && pass "no password hash in any admin response" || fail "a hash leaked"

echo
echo "== 11. brand and assets =="
BODY=$(curl -s -b "$JAR" http://127.0.0.1:$PORT/admin/login)
grep -q "logo.svg" <<<"$BODY" && pass "brand wordmark is used" || fail "wordmark missing"
grep -qE "greatapi\.css\?v=$VERSION" <<<"$BODY" && pass "assets are cache-busted by version" || fail "no cache busting"
EXTERNAL=$(grep -oE 'https?://[^"]+' <<<"$BODY" | grep -v "127.0.0.1" || true)
[ -z "$EXTERNAL" ] && pass "nothing loaded from a CDN" || fail "external asset: $EXTERNAL"
CSS=$(curl -s "http://127.0.0.1:$PORT/admin/_static/greatapi.css")
grep -q "0055ff" <<<"$CSS" && pass "brand blue #0055FF in the stylesheet" || fail "brand colour missing"
[ "$(wc -c <<<"$CSS")" -gt 15000 ] && pass "stylesheet shipped intact ($(wc -c <<<"$CSS") bytes)" || fail "stylesheet truncated"

echo
echo "== 12. sorting =="
check "sort by a visible column" \
  "$(curl -s -b "$JAR" -o /dev/null -w '%{http_code}' "http://127.0.0.1:$PORT/admin/model/auth/greatapi_user?sort=username&dir=asc")" "200"
check "reject a malformed direction" \
  "$(curl -s -b "$JAR" -o /dev/null -w '%{http_code}' "http://127.0.0.1:$PORT/admin/model/auth/greatapi_user?sort=username&dir=DROP")" "422"
curl -s -b "$JAR" "http://127.0.0.1:$PORT/admin/model/auth/greatapi_user?sort=hashed_password" \
  | grep -q "hashed_password" && fail "redacted column reachable via sort" || pass "redacted column not sortable"

echo
echo "== 13. CSRF =="
check "POST without a token" \
  "$(curl -s -b "$JAR" -o /dev/null -w '%{http_code}' -d 'name=x' http://127.0.0.1:$PORT/admin/api-keys)" "403"

echo
echo "== 14. the application API works =="
CREATED=$(curl -s -X POST "http://127.0.0.1:$PORT/catalog/items" \
  -H 'content-type: application/json' -d '{"title":"QA widget","body":"hello"}')
grep -q '"title":"QA widget"' <<<"$CREATED" && pass "POST /catalog/items" || fail "POST /catalog/items: $CREATED"
check "GET /docs" "$(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:$PORT/docs)" "200"
check "GET /openapi.json" "$(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:$PORT/openapi.json)" "200"

echo
echo "== 15. no errors in the server log =="
if grep -qiE "traceback|error|exception" server.log; then
  fail "server log has errors:"; grep -iE "traceback|error|exception" server.log | head -5
else
  pass "server log is clean"
fi

echo
if [ "$FAIL" = 0 ]; then
  printf "\033[32mALL QA CHECKS PASSED -- ready to ship\033[0m\n"
else
  printf "\033[31mQA FAILURES ABOVE\033[0m\n"; exit 1
fi
