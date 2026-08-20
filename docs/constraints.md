# Every specified constraint, and the code that enforces it

Generated from `tests/test_constraints.py`, which asserts that each enforcer
named here exists and that the module holding it is reachable from production
code. The table cannot drift from the checks because the checks read this
table's data.

It exists because one defect class produced four instances in a single day —
a rule written down, agreed, and never made into a gate. Each was found by
accident, after it had already cost something: an exam with 63% duplicate
packets, another with half its packets outside the specified record range.

## Enforced

| Source | Constraint | Enforced by | Reported as |
|---|---|---|---|
| SECURITY.md | no network call is reachable at inference | `consylr.offline.no_network` | NetworkAttempted |
| RFC-0001 | `open[].need` at most 120 characters | `consylr.schema.NEED_MAX` | need_too_long |
| RFC-0001 | output fields are a closed set | `consylr.schema.FIELDS` | unknown_field |
| RFC-0001 | certainty is one of three words, never a number | `consylr.schema.CERTAINTIES` | bad_certainty |
| RFC-0001 | exception kind is from the frozen family list | `consylr.schema.KINDS` | bad_kind |
| RFC-0001 | disposition act is one of four | `consylr.schema.ACTS` | bad_act |
| RFC-0001 | every cited identifier resolves in the packet | `consylr.schema.validate` | unresolved_id |
| RFC-0001 | residue is exactly the records in no supported or ambiguous match | `consylr.schema.validate` | residue_wrong |
| RFC-0001 | a request disposition is covered by an open entry | `consylr.schema.validate` | dangling_request |
| RFC-0001 | a supported claim cites evidence | `consylr.schema.validate` | uncited_claim |
| RFC-0001 | a Gate 1 packet holds 5 to 10 records | `consylr.cases.PACKET_RECORDS` | packet_too_small / packet_too_large |
| RFC-0001 | rendered prompt within its token cap | `consylr.budget.check` | prompt_over_budget |
| RFC-0001 | generation headroom reserved | `consylr.budget.check` | headroom_lost |
| RFC-0002 | a case belongs to exactly one family | `consylr.templates.check` | unknown_family; one family per template by construction |
| RFC-0002 | clearly-supported cases are 65-75% of the mix | `consylr.quota.check` | supported_share_low / supported_share_high |
| RFC-0002 | cases declining for an unestablished cause are 10-15% of the mix, counted from the answer | `consylr.quota.check` | abstention_share_low / abstention_share_high |
| RFC-0002 | unsupported cases are 3-10% of the mix | `consylr.quota.check` | unsupported_share_low / unsupported_share_high |
| RFC-0002 | every family present in measurable numbers | `consylr.quota.check` | family_below_floor |
| RFC-0002 | a family's answer cannot contradict its certainty | `consylr.quota.check` | contradictory_certainty |
| RFC-0003 | a template is a closed world | `consylr.templates.shape_violations` | unknown_field / missing_field / bad_type |
| RFC-0003 | a packet is within the packet allowance | `consylr.budget.check_packet` | packet_over_budget |
| RFC-0003 | every case from one template lands in exactly one role | `consylr.corpus.check` | packet_in_two_roles |
| RFC-0003 | no two cases share a packet under different answers | `consylr.corpus.check` | contradictory_ground_truth |
| RFC-0003 | near-duplicate detection over the corpus | `consylr.corpus.check` | duplicate_packet |
| RFC-0003 | one scenario is not two templates | `consylr.identity.check` | duplicate_scenario |
| RFC-0003 | a template that emits no case is reported | `consylr.identity.check` | unbuildable_template |
| RFC-0003 | the answer describes the packet it was built from | `consylr.cases._prove_effect` | raises; a defect in the generator, not the corpus |
| RFC-0003 | the packet carries the cause its family is graded on | `consylr.cases._prove_cause` | raises; authoring lint, backed by the byte check |
| RFC-0003 | a corpus binds to the prompt template it was rendered against | `consylr.prompt.DIGEST` | recorded per case as prompt_digest |
| RFC-0003 | an exam cannot silently change between runs | `consylr.corpus.content_digest` | asserted by a scoring run before it scores |
| RFC-0003 | the budget's own numbers fit the context | `consylr.budget.Budget.validate` | raises at construction |
| RFC-0003 | amounts are written one way | `consylr.money.canonical` | applied to every record at construction |

## Specified, deliberately not enforced

A constraint measured rather than gated is a legitimate state. A constraint
nobody decided about is not — so each of these carries its reason.

| Source | Constraint | Why there is no gate |
|---|---|---|
| RFC-0001 | structured-output parse rate at or above 99% | a property of the trained model, measured by the evaluation (#23), not of a corpus |
| RFC-0001 | amount/reference/date exact-copy rate at or above 99.5% | measured at evaluation; the corpus cannot constrain what the model copies |
| RFC-0001 | evidence citation precision at or above 98% | measured at evaluation (#23); the corpus side is `_clean` citing its own records |
| RFC-0001 | correct abstention at or above 90%, false abstention under 5% | measured at evaluation (#16); the corpus side is the quota bands above |
| RFC-0001 | output fits inside 256 generation tokens | a property of model output; the corpus side is the reserved headroom |
| RFC-0003 | 300 to 500 gold scenario templates | a target for corpus size, not a property of a valid corpus; 350 authored |
| RFC-0003 | 8,000 to 15,000 training examples | NOT MET at Gate 1 and stated plainly: a template yields as many distinct cases as its deformation can distinguish, so this needs per-case instantiation (#20). Padding to the number would mean duplicates, which the writer now refuses. |
| RFC-0003 | the sealed set is never paraphrased | paraphrase is not implemented; the refusal cannot be violated by absent code |
