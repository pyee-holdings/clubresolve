# TODOS

## Analytics Integration
**What:** Add PostHog or Mixpanel to track wizard funnel metrics (intake started, intake completed, action plan generated, print/save clicked).
**Why:** Currently no visibility into how users interact with the wizard. Need data to optimize conversion and identify drop-off points.
**Pros:** Enables data-driven product decisions, measures actual usage patterns.
**Cons:** Adds a third-party dependency, requires privacy policy update, minor performance impact from tracking script.
**Context:** The wizard MVP launches without analytics. Simple server-side logging captures whether plans were generated, but not frontend behavior (which step users drop off at, how long they spend on each step, whether they print/save the result). PostHog is recommended for its open-source option and session replay capability.
**Depends on:** Wizard MVP shipped and receiving traffic.
