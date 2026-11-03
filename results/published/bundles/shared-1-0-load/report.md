NANDA Town System Fitness Report
========================================
Run:       sim-005245d384d0
Scenario:  resilience-shared (seed 0)
Faults:    none
Agents:    experiment (resilience_clock), backend-0 (resilience_backend), backend-1 (resilience_backend), backend-2 (resilience_backend), backend-3 (resilience_backend), provider-00 (resilience_provider), provider-01 (resilience_provider), provider-02 (resilience_provider), provider-03 (resilience_provider), provider-04 (resilience_provider), provider-05 (resilience_provider), provider-06 (resilience_provider), provider-07 (resilience_provider), provider-08 (resilience_provider), provider-09 (resilience_provider), provider-10 (resilience_provider), provider-11 (resilience_provider), buyer-00 (resilience_buyer), buyer-01 (resilience_buyer), buyer-02 (resilience_buyer), buyer-03 (resilience_buyer), buyer-04 (resilience_buyer), buyer-05 (resilience_buyer), buyer-06 (resilience_buyer), buyer-07 (resilience_buyer)
Releases:  evaluator lab-0.2.6, nanda_resilience 0.1.0, nandatown 0.2.0, nandatown_commit b7adc6121868742cf0f00cfebbf2d38bdb349057, python 3.12.10, resilience_evaluator resilience.v2
Duration:  44.0 logical seconds, deterministic
Verdict:   PASSED
Rerun:     nanda-resilience run --condition shared --policy load --seed 0 --disclosure 1.0 --out NEW_DIRECTORY

The journey: bring, connect, attempt, disrupt, inspect, improve.

Stages (each one a separate claim with its own failure boundary):
  resilience.v2     Passed                [ev-4087]
                    note: Replayed 160 tasks, 288 attempts; 104 tasks succeeded. Pass means evidence is internally consistent, not that this policy is resilient or dependencies are truthful.
  ledger_conserved  Passed               money was conserved across every movement [ev-199, ev-203, ev-207, ev-211, ev-215, ev-219, ev-223, ev-227]
                    note: 3200 cents conserved across every movement
  privacy           Not tested           not exercised in this run
                    note: no redaction declared by this scenario

Events recorded: 4088. Intents recorded: 1568.
This result applies only to the named agents, releases, scenario, failure, evaluator, and time window.
One run is one scoped observation, not a certificate.
Improve: fix what failed and rerun the same profile.
