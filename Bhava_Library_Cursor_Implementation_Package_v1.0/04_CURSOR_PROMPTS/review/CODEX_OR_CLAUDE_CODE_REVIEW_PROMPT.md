# Independent Engineering Review Prompt

Act as an independent senior reviewer. Do not modify code until the review report is complete.

Review the Bhāva Library repository for:

- requirements coverage;
- accidental binary tracking;
- source parser correctness;
- respectful network behavior;
- access-control boundaries;
- disk exhaustion;
- partial-download corruption;
- resume correctness;
- path traversal;
- archive safety;
- direct-object exposure;
- database consistency;
- state-machine violations;
- hidden test failures;
- misleading reports;
- copyright ownership confusion;
- third-party original modification;
- Windows portability;
- backup and restore;
- documentation truthfulness.

Re-run all automated gates. Add adversarial tests for every high-risk path.

Return:

1. findings by severity;
2. evidence and reproduction;
3. false assumptions;
4. missing requirements;
5. test results;
6. required fixes;
7. final verdict: BLOCK, CONDITIONAL PASS, or PASS.

Never claim PASS with unresolved critical or high findings.
