# Mizan Retail

Frappe app for Mizan, an Egyptian retail ERP built on ERPNext 16. One company, many branches:
each branch is one Warehouse plus one POS Profile (till) tied to it.

- `mizan_retail.branches.create_branch(company, branch_name)` creates the branch and returns
  `{"warehouse": ..., "pos_profile": ...}`.
- `mizan_retail.branches.delete_branch(company, branch_name)` removes it; refused while the
  branch warehouse holds stock or has stock ledger entries.
- Desk page **Add Branch** (`/app/add-branch`) calls `create_branch`. It is linked from the
  **Mizan Retail** workspace and sidebar, whose icon sits on ERPNext's left icon bar.
- Each branch till (POS Profile) carries the company's default sales tax template (mizan_core's
  "Egypt VAT"), so till sales charge VAT.

Requires ERPNext 16 and `mizan_core`. License: GPL-3.0 (see `license.txt`).

Arabic translations: `mizan_retail/locale/ar.po`. After editing it on a bench, run
`bench compile-po-to-mo --app mizan_retail` (the edition image build compiles it itself).

## Tests

    bench --site <site> run-tests --app mizan_retail
