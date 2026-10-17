# AI Jana / Jana Academy corpus plan

Date: 2026-10-17. Scope: five Russian-language demonstration documents. All application claims are about the current Digital HR prototype, not Jana Post policy.

| Document | Main evidence | Sections | Intended scope |
| --- | --- | --- | --- |
| HR-01 | Request routes, lifecycle, notifications, mock 1C | Submission; decisions; tracking; changes; limits | all |
| HR-02 | Authentication/profile, seed, Academy, assistant | Entry; profile; services; learning; assistant | all |
| LMS-01 | Course/assignment models and Academy routes | Assignment; progress; quiz; rewards; assistant | all |
| LOG-01 | GS1 receiving/inspection and OSHA handling guidance | Receiving; inspection; sorting; storage; handling | all |
| LOG-02 | UPU tracking and GS1 transport status | Lifecycle; events; handoffs; exceptions; demo example | hr_admin (synthetic test scope) |

The `LOG-02` restriction is a **DEMO / SYNTHETIC access assignment** for testing role filtering. The material is general education and is not confidential Jana Post operating information. The existing `knowledge_documents.access_scope` accepts one role or `all`; `hr_admin` allows a clear denied-access case without changing schema or business roles.

Unsupported claims excluded: approved Jana Post leave policy, entitlements, deadlines, benefits, employee contacts, actual warehouse procedures or tracking event codes, real 1C/Documentolog connectivity, production learning assignments, and a complete original Challenge 02 brief. The repository contains team interpretations and code; the public organizer page describes only the high-level Digital HR challenge.

No chatbot question-answer pairs will appear in the documents. Stable citation anchors will use `HR-01 §1.1` style. Evaluation questions will be kept separately.
