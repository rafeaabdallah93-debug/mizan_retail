# Online store (WooCommerce) with Mizan

## For the owner

Mizan works fully without a website. If you do not sell online, nothing here applies to you and nothing extra is installed.

If you have a WooCommerce website, we add one extra piece, the WooCommerce connector (`woocommerce_fusion`), installed exactly as published, with no changes.

What it does:

- **Stock goes one way, from Mizan to the website.** The website never changes your stock in Mizan.
- **Prices go one way too**, from one Mizan price list to the website. There are no different prices per branch online.
- **Website orders arrive in Mizan as Sales Orders.** All of them are booked in ONE warehouse of ONE company. The connector does not pick the nearest branch and does not split an order between branches.
- The website shows the **sum** of the stock of the warehouses you choose.

**Our recommendation: create one warehouse called "Online".** Move to it only the stock you want to sell on the website (a normal stock transfer from a branch). The website then shows exactly what is in Online, and orders are taken from Online. Branch cash-register sales cannot silently use up stock the website already promised.

What this means for you:

- Someone must own the job of moving stock into Online.
- If you tick all branches instead, the website may show "5 in stock" when those 5 are spread over 5 branches, while orders are booked on one warehouse. That can oversell.
- Delivery from the nearest branch, or click-and-collect per branch, is not supported by the connector. It would need custom work.

> SECURITY WARNING: do not put the website edition live yet.
> The connector's check of the webhook secret is switched off in its code. The "new order" address on your Mizan server therefore accepts requests that are not signed by WooCommerce. See the technical section. This must be fixed by the connector's authors, or patched, before any customer goes live.

## Technical setup

### Security warning (blocker for go-live)

`woocommerce_fusion/woocommerce_endpoint.py`, lines 29-34 (branch `version-16`, commit `ab71a15`): the HMAC signature comparison against the `x-wc-webhook-signature` header is commented out. The HMAC is computed and never compared. The endpoint `order_created` is `allow_guest=True` and then runs as the server's `creation_user`, identified only by the `x-wc-webhook-source` header. Anyone who knows the site's domain can post a fake "order created" event. The sync fetches the order from the real WooCommerce API by id, which limits the damage, but it can still trigger syncs.

Until it is fixed upstream or patched: do not take the website edition live. Mizan has deliberately NOT patched the connector. Interim mitigation options: do not create the webhook (orders then arrive on the hourly sync), or block the `order_created` path at the reverse proxy for everyone except the WooCommerce server's IP.

### Requirements

- Connector: `Starktail/woocommerce_fusion`, branch `version-16` (app version 2.3.0), installed unchanged. It needs Frappe and ERPNext `>=16,<17` and Python `>=3.14`. It declares no `required_apps`, so install ERPNext first.
- Python packages: `woocommerce~=3.0.0`, `jsonpath-ng~=1.7.0` (pulls in `ply`). Install them in the bench environment (`pip install` in production).
- Scheduler enabled and workers running, including the `long` queue. The connector uses `hourly_long` (orders and products), `daily_long` (stock and prices) and a per-minute job (batch API queue).
- WooCommerce REST API key with Read/Write permission (WordPress admin, WooCommerce, Settings, Advanced, REST API). The site must be reachable over HTTPS from the Mizan server.
- Optional "Order created" webhook in WooCommerce, pointing at the connector's `order_created` endpoint, using the server's generated secret. Without it, orders arrive at the next hourly run. See the security warning above.

### How a website maps to a warehouse

Everything lives on one **WooCommerce Server** record per website (all settings are per server).

| Setting | What it controls |
| --- | --- |
| `company` | Company of the Sales Orders created from website orders. |
| `warehouse` | The single warehouse set on every line of every website Sales Order. If empty, order creation fails. |
| `warehouses` (table) | Warehouses whose stock is summed (`Bin.actual_qty`) and pushed to the website. Only used when `enable_stock_level_synchronisation` is on. |
| `price_list` | Price List pushed to the WooCommerce Regular Price (with `enable_price_list_sync`). |
| `enable_sync` | Master switch. Nothing runs unless it is ticked. |
| `creation_user` | The user the webhook runs as. Use a restricted user. |

`warehouse` (orders) and `warehouses` (stock sync) are separate fields. Nothing forces them to agree. Set both deliberately.

### Recommended configuration

1. Create an "Online" warehouse under the one company (not a POS Profile warehouse).
2. On the WooCommerce Server record: `company` = the Mizan company, `warehouse` = Online, `warehouses` = Online only, stock sync on. Turn on `subtract_reserved_stock` only if Stock Reservation is enabled in Stock Settings.
3. Create a Price List for the website (for example "Online Retail"), set it as `price_list`, turn on price sync.
4. Set `creation_user` and `delivery_after_days`. Set `wc_last_sync_date` in WooCommerce Integration Settings (order sync raises an error while it is empty).
5. Confirm the scheduler is on. Handle the webhook signature gap above before creating the webhook.
6. Test on staging: a branch POS sale, a website order, a transfer into Online. Check the website stock after each.

### Multi-branch limits

- One warehouse per website for orders: no routing by city, branch or availability, no split fulfilment.
- The website stock is a plain sum of the ticked warehouses. Ticking all branches can oversell, because the order is still booked on the one `warehouse`.
- No safety-stock buffer per warehouse. No per-branch price: one Price List per website.
- Stock is pushed when Stock Entry, Stock Reconciliation, Delivery Note or Sales Invoice (with Update Stock) is submitted or cancelled, and once a day. POS Invoices are not hooked directly; they reach the website when consolidated into a Sales Invoice or at the daily run (inferred from the hook list, verify on staging).
- Stock quantity is rounded down and sent as a whole number.
- The connector's own doc says "all warehouses". The code sums only the ticked ones. Trust the code.
- The connector creates the Sales Order only. Delivery Note and Sales Invoice follow Mizan's normal flow.
- If stock sync is on and no warehouse is ticked, every linked product is pushed as 0 stock.

### Local test site (developers)

In `mizan-dev`, the connector lives only on `shop.localhost`; `dev.localhost` must not have it. It is cloned to `custom-apps/woocommerce_fusion` (`--branch version-16 --depth 1`), which adds it to PYTHONPATH for all services (so it is importable everywhere, but installed only on `shop.localhost`). Do not use `install-custom-app.sh` for it, because that installs onto `dev.localhost`.

The script does not install Python dependencies. In the dev containers, `pip install` fails TLS through the proxy, so the wheels (`WooCommerce-3.0.0`, `jsonpath_ng-1.7.0`, `ply-3.11`) were downloaded on the host, copied into each Frappe container (backend, queue-short, queue-long, scheduler, websocket) and installed with `/home/frappe/frappe-bench/env/bin/python -m pip install --no-deps --no-index <wheels>`. This is lost when containers are recreated and must be repeated.

Site setup: `bench new-site shop.localhost --admin-password admin --db-root-password admin --install-app erpnext`, `set-config allow_tests true`, then `install-app` for `mizan_core`, `mizan_retail`, `woocommerce_fusion`.

Guard: `mizan_retail/tests/test_without_woocommerce.py` asserts the connector is not installed on the site and `create_branch` still works (it skips itself on a site that has the connector).
