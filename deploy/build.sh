#!/usr/bin/env bash
# Build the Mizan image for one edition.
#
#   deploy/build.sh shop     [ENV_FILE]
#   deploy/build.sh shop-web [ENV_FILE]
#
# Apps come from deploy/versions.env (git URL or local checkout + commit); any value
# there can be overridden by an environment variable of the same name. Each app is
# exported with `git archive` at that one commit, so uncommitted changes are never
# baked in. The image is tagged mizan-<edition>:<short SHAs> (never "latest").
# If ENV_FILE is given, its MIZAN_IMAGE= line is set to the new tag.
set -euo pipefail

EDITION="${1:?usage: $0 shop|shop-web [ENV_FILE]}"
ENV_FILE="${2:-}"
case "$EDITION" in
  shop)     APPS="mizan_core mizan_retail" ;;
  shop-web) APPS="mizan_core mizan_retail woocommerce_fusion" ;;
  *) echo "Unknown edition '$EDITION' (use shop or shop-web)" >&2; exit 2 ;;
esac

DEPLOY="$(cd "$(dirname "$0")" && pwd)"
REPO="$(cd "$DEPLOY/.." && pwd)"   # the mizan_retail checkout

# Load defaults without overriding values already set in the environment.
while IFS='=' read -r key val; do
  [[ "$key" =~ ^[A-Z_]+$ ]] || continue
  [ -n "${!key:-}" ] || export "$key=$val"
done < "$DEPLOY/versions.env"

ls "$DEPLOY"/wheels/*.whl >/dev/null 2>&1 || "$DEPLOY/fetch-wheels.sh"

CTX="$DEPLOY/.build/$EDITION"
rm -rf "$CTX"; mkdir -p "$CTX/apps" "$CTX/requirements"
cp -a "$DEPLOY/wheels" "$CTX/wheels"
cp "$DEPLOY/requirements/build.txt" "$CTX/requirements/"

declare -A SHA
for app in $APPS; do
  var="$(echo "$app" | tr a-z A-Z)"
  src_var="${var}_SRC"; ref_var="${var}_REF"
  src="${!src_var}"; ref="${!ref_var}"
  # Relative local paths are relative to the mizan_retail checkout.
  if [[ "$src" != *://* && "$src" != git@* && "$src" != /* ]]; then src="$REPO/$src"; fi
  if [[ "$src" == *://* || "$src" == git@* ]]; then
    gitdir="$DEPLOY/.build/src/$app.git"
    [ -d "$gitdir" ] || git clone --quiet --bare "$src" "$gitdir"
    git -C "$gitdir" fetch --quiet origin "+refs/heads/*:refs/heads/*" "+refs/tags/*:refs/tags/*" || true
    git -C "$gitdir" cat-file -e "$ref^{commit}" 2>/dev/null || git -C "$gitdir" fetch --quiet origin "$ref"
  else
    gitdir="$src"
    if [ -n "$(git -C "$gitdir" status --porcelain --untracked-files=no)" ]; then
      echo "Note: $gitdir has uncommitted changes; they are NOT included (building $ref)." >&2
    fi
  fi
  sha="$(git -C "$gitdir" rev-parse --verify "$ref^{commit}")"
  SHA[$app]="$sha"
  mkdir -p "$CTX/apps/$app"
  git -C "$gitdir" archive --format=tar "$sha" | tar -x -C "$CTX/apps/$app"
  rm -rf "$CTX/apps/$app/deploy"   # packaging files are not app code
  [ -f "$DEPLOY/requirements/$app.txt" ] && cp "$DEPLOY/requirements/$app.txt" "$CTX/requirements/"
  echo "$app  $sha  (from $src)"
done

TAG="${SHA[mizan_retail]:0:7}-${SHA[mizan_core]:0:7}"
[ -n "${SHA[woocommerce_fusion]:-}" ] && TAG="$TAG-${SHA[woocommerce_fusion]:0:7}"
IMAGE="mizan-$EDITION:$TAG"

docker build -f "$DEPLOY/Dockerfile" -t "$IMAGE" \
  --build-arg EDITION="$EDITION" \
  --build-arg MIZAN_CORE_SHA="${SHA[mizan_core]}" \
  --build-arg MIZAN_RETAIL_SHA="${SHA[mizan_retail]}" \
  --build-arg WOOCOMMERCE_FUSION_SHA="${SHA[woocommerce_fusion]:-}" \
  "$CTX"
rm -rf "$CTX"

if [ -n "$ENV_FILE" ]; then
  if grep -q '^MIZAN_IMAGE=' "$ENV_FILE"; then
    sed -i "s|^MIZAN_IMAGE=.*|MIZAN_IMAGE=$IMAGE|" "$ENV_FILE"
  else
    echo "MIZAN_IMAGE=$IMAGE" >> "$ENV_FILE"
  fi
  echo "Set MIZAN_IMAGE=$IMAGE in $ENV_FILE"
fi
echo "Built $IMAGE"
