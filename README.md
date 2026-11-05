# Mizan Retail

Frappe app for Mizan, an Egyptian retail ERP built on ERPNext 16. One company, many branches:
each branch is one Warehouse plus one POS Profile (till) tied to it.

- `mizan_retail.branches.create_branch(company, branch_name)` creates the branch and returns
  `{"warehouse": ..., "pos_profile": ...}`.
- `mizan_retail.branches.delete_branch(company, branch_name)` removes it; refused while the
  branch warehouse holds stock or has stock ledger entries.
- Desk page **Add Branch** (`/app/add-branch`) calls `create_branch`.

Requires ERPNext 16 and `mizan_core`. License: GPL-3.0.

## Tests

    bench --site <site> run-tests --app mizan_retail
