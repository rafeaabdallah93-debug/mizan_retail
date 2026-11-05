# Mizan image: the pinned ERPNext 16 image plus the Mizan apps (and, for the
# shop-web edition, the WooCommerce connector), with their Python dependencies
# and static files baked in.
#
# Do not run `docker build` on this file directly: use deploy/build.sh, which
# exports each app at an exact git commit into a build context laid out as
#   apps/<app>/            app source (git archive of one commit)
#   requirements/*.txt     hash-pinned wheels to install (build.txt always)
#   wheels/                the wheels themselves (from deploy/fetch-wheels.sh)
# and passes the commits below as build args (recorded as image labels).

# Exact tag, plus the digest, so the base can never change under us.
ARG BASE_IMAGE=frappe/erpnext:v16.53.0@sha256:b961d69ed3265f44f712f40be58a3e6a22c8662f61a7e1a8097765534e3e9be2
FROM ${BASE_IMAGE}

ARG EDITION
ARG MIZAN_CORE_SHA
ARG MIZAN_RETAIL_SHA
ARG WOOCOMMERCE_FUSION_SHA=""

LABEL org.opencontainers.image.title="mizan-${EDITION}" \
      mizan.edition="${EDITION}" \
      mizan.base="frappe/erpnext:v16.53.0" \
      mizan.mizan_core.sha="${MIZAN_CORE_SHA}" \
      mizan.mizan_retail.sha="${MIZAN_RETAIL_SHA}" \
      mizan.woocommerce_fusion.sha="${WOOCOMMERCE_FUSION_SHA}"

USER frappe
WORKDIR /home/frappe/frappe-bench

COPY --chown=frappe:root requirements/ /tmp/mizan/requirements/
COPY --chown=frappe:root wheels/ /tmp/mizan/wheels/
COPY --chown=frappe:root apps/ /tmp/mizan/apps/

# 1. Offline, hash-checked install of the wheels (build backend + connector deps).
# 2. Each app goes into apps/ and is installed editable, exactly like bench does,
#    without dependencies and without network.
# 3. Each app's public/ folder is linked into the baked assets folder, which the
#    image's entrypoint links to sites/assets on every container start, so nginx
#    serves /assets/<app>/... with no runtime steps. (These apps ship plain JS/CSS
#    files, no bundles, so no `bench build` is needed.)
# 4. Each app's translations (<app>/locale/<lang>.po) are compiled to
#    assets/locale/<lang>/LC_MESSAGES/<app>.mo, where Frappe 16 reads them; this
#    is the part of `bench build` these apps need.
# 5. sites/apps.txt lists frappe and erpnext first, then the added apps.
RUN set -eu; \
    for req in /tmp/mizan/requirements/*.txt; do \
      env/bin/python -m pip install --no-cache-dir --no-index --no-deps \
        --find-links /tmp/mizan/wheels --require-hashes -r "$req"; \
    done; \
    printf 'frappe\nerpnext\n' > sites/apps.txt; \
    for src in /tmp/mizan/apps/*/; do \
      app="$(basename "$src")"; \
      cp -a "$src" "apps/$app"; \
      env/bin/python -m pip install --no-cache-dir --no-index --no-deps \
        --no-build-isolation -e "apps/$app"; \
      if [ -d "apps/$app/$app/public" ]; then \
        ln -sfn "/home/frappe/frappe-bench/apps/$app/$app/public" "assets/$app"; \
      fi; \
      for po in apps/$app/$app/locale/*.po; do \
        [ -f "$po" ] || continue; \
        lang="$(basename "$po" .po)"; \
        mkdir -p "assets/locale/$lang/LC_MESSAGES"; \
        env/bin/python -c 'import sys; from babel.messages.pofile import read_po; from babel.messages.mofile import write_mo; write_mo(open(sys.argv[2], "wb"), read_po(open(sys.argv[1], "rb")))' \
          "$po" "assets/locale/$lang/LC_MESSAGES/$app.mo"; \
        echo "compiled $po"; \
      done; \
      echo "$app" >> sites/apps.txt; \
    done; \
    rm -rf /tmp/mizan; \
    for app in $(cat sites/apps.txt); do env/bin/python -c "import $app" ; done; \
    cat sites/apps.txt
