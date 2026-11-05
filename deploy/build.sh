#!/usr/bin/env bash
# Build the Mizan image for one edition.
#
#   deploy/build.sh shop     [ENV_FILE]
#   deploy/build.sh shop-web [ENV_FILE]
#
# Needs: bash (3.2 or later: Linux, macOS, or WSL2 on Windows), git and Docker.
# Apps come from deploy/versions.env (git URL or local checkout + commit); any value
# there can be overridden by an environment variable of the same name. Each app is
# exported with `git archive` at that one commit, so uncommitted changes are never
# baked in. The image is tagged mizan-<edition>:<short SHAs> (never "latest").
# If ENV_FILE is given, its MIZAN_IMAGE= line is set to the new tag.
set -eu

EDITION="${1:-}"
ENV_FILE="${2:-}"
case "$EDITION" in
  shop)     APPS="mizan_core mizan_retail" ;;
  shop-web) APPS="mizan_core mizan_retail woocommerce_fusion" ;;
  *) echo "usage: $0 shop|shop-web [ENV_FILE]" >&2; exit 2 ;;
esac

DEPLOY="$(cd "$(dirname "$0")" && pwd)"
REPO="$(cd "$DEPLOY/.." && pwd)"   # the mizan_retail checkout

# Load defaults without overriding values already set in the environment.
while IFS='=' read -r key val; do
  case "$key" in ''|\#*) continue ;; esac
  if [ -z "${!key:-}" ]; then export "$key=$val"; fi
done < "$DEPLOY/versions.env"

ls "$DEPLOY"/wheels/*.whl >/dev/null 2>&1 || bash "$DEPLOY/fetch-wheels.sh"

CTX="$DEPLOY/.build/$EDITION"
rm -rf "$CTX"; mkdir -p "$CTX/apps" "$CTX/requirements"
cp -R "$DEPLOY/wheels" "$CTX/wheels"
cp "$DEPLOY/requirements/build.txt" "$CTX/requirements/"

SHA_mizan_core=""; SHA_mizan_retail=""; SHA_woocommerce_fusion=""
for app in $APPS; do
  var="$(echo "$app" | tr '[:lower:]' '[:upper:]')"
  src_var="${var}_SRC"; ref_var="${var}_REF"
  src="${!src_var}"; ref="${!ref_var}"
  case "$src" in
    *://*|git@*) remote=1 ;;
    /*) remote=0 ;;
    *) remote=0; src="$REPO/$src" ;;   # relative to the mizan_retail checkout
  esac
  if [ "$remote" = 1 ]; then
    gitdir="$DEPLOY/.build/src/$app.git"
    [ -d "$gitdir" ] || git clone --quiet --bare "$src" "$gitdir"
    git -C "$gitdir" fetch --quiet origin "+refs/heads/*:refs/heads/*" "+refs/tags/*:refs/tags/*" || true
    git -C "$gitdir" cat-file -e "$ref^{commit}" 2>/dev/null || git -C "$gitdir" fetch --quiet origin "$ref"
  else
    gitdir="$src"
    if [ -n "$(git -C "$gitdir" status --porcelain --untracked-files=no)" ]; then
      echo "WARNING: $gitdir has uncommitted changes; they are NOT included (building $ref)." >&2
    fi
  fi
  sha="$(git -C "$gitdir" rev-parse --verify "$ref^{commit}")"
  if [ "$ref" != "$sha" ] && ! git -C "$gitdir" describe --exact-match --tags "$sha" >/dev/null 2>&1; then
    echo "WARNING: $app: '$ref' is not a pinned SHA or a tag; building untagged commit $sha." >&2
    echo "         Record it in deploy/versions.env (${var}_REF=$sha) to rebuild the same image." >&2
  fi
  eval "SHA_$app=\$sha"
  mkdir -p "$CTX/apps/$app"
  git -C "$gitdir" archive --format=tar "$sha" | tar -x -C "$CTX/apps/$app"
  rm -rf "$CTX/apps/$app/deploy"   # packaging files are not app code
  if [ -f "$DEPLOY/requirements/$app.txt" ]; then cp "$DEPLOY/requirements/$app.txt" "$CTX/requirements/"; fi
  echo "$app  $sha  (from $src)"
done

short() { echo "$1" | cut -c1-7; }
TAG="$(short "$SHA_mizan_retail")-$(short "$SHA_mizan_core")"
if [ -n "$SHA_woocommerce_fusion" ]; then TAG="$TAG-$(short "$SHA_woocommerce_fusion")"; fi
IMAGE="mizan-$EDITION:$TAG"

docker build -f "$DEPLOY/Dockerfile" -t "$IMAGE" \
  --build-arg EDITION="$EDITION" \
  --build-arg MIZAN_CORE_SHA="$SHA_mizan_core" \
  --build-arg MIZAN_RETAIL_SHA="$SHA_mizan_retail" \
  --build-arg WOOCOMMERCE_FUSION_SHA="$SHA_woocommerce_fusion" \
  "$CTX"
rm -rf "$CTX"

if [ -n "$ENV_FILE" ]; then
  # Portable in-place edit (no sed -i); `cat >` keeps the file's permissions.
  tmp="$ENV_FILE.tmp.$$"
  awk -v line="MIZAN_IMAGE=$IMAGE" '
    /^MIZAN_IMAGE=/ { print line; done = 1; next }
    { print }
    END { if (!done) print line }' "$ENV_FILE" > "$tmp"
  cat "$tmp" > "$ENV_FILE"
  rm -f "$tmp"
  echo "Set MIZAN_IMAGE=$IMAGE in $ENV_FILE"
fi
echo "Built $IMAGE"
