# Direct DELETE receipts do not bind the transitive effect

The authored corpus declares an SQLite self-referencing forest with ON DELETE CASCADE and an exact stable-ID contract: after deleting specified roots, remove their descendant closure while preserving all surviving rows. The independent oracle is ordinary graph reachability on authored parent IDs, not RETURNING or SQLite's foreign_key_check. The test commits, closes and reopens the actual SQLite store before measuring surviving ID-to-row values.

A and B differ in one dependency: row 3 hangs from removed row 2 in A but from protected row 4 in B. Both native DELETE ... RETURNING receipts contain only root 1. With foreign keys enabled, A persists removals {1,2,3}; B persists {1,2}. Both pass foreign_key_check. With enforcement off, identical direct receipts are still reported, yet only 1 is removed and the surviving child is orphaned. These two intervention types distinguish wrong connection policy from changed destination lineage. Sixty-four seeded authored forests independently check the closure result and preserved survivors.

The fixture extends a scoped overwrite/preserve receipt: once effects depend on relationships, source action, direct affected IDs and prior values of named targets are not sufficient to bind output. Either independently pin the action policy and compute the relevant dependency closure, or verify the full claimed effect against committed durable state. A pass on referential integrity alone cannot establish the intended set of removals. This is a forest with a single declarative dependency and no application triggers, deferred changes across concurrent writers, or production workload claim.

Replay: `python3 -IB check.py | cmp - result.json`.
