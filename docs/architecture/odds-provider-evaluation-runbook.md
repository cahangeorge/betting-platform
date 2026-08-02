# Licensed odds provider evaluation and approval runbook

Updated: 2026-08-01. Re-check official sources immediately before purchase or
activation because pricing, coverage and terms can change.

## Technical ordering

1. **Primary offline implementation candidate: Sportmonks Football API v3
   Standard Odds.** It exposes football-native fixture/league/bookmaker/market
   IDs and a fixed 10-second latest-update endpoint. Official guidance says a
   no-change interval returns HTTP 200 with an empty data array and recommends a
   10-second poll. Standard odds must be snapshotted locally.
2. **Future shadow/historical candidate: The Odds API v4.** It offers a simpler
   multi-sport event/bookmaker/market contract and paid historical snapshots,
   but credit cost multiplies by markets and regions and it lacks a public delta
   endpoint.
3. **Bounded fallback: OddsHarvester/OddsPortal.** It remains browser-isolated,
   approval-required and never becomes an implicit substitute for licensed API
   rights.

This ordering does not authorize credentials or live traffic.

## Current comparison

| Dimension | Sportmonks v3 | The Odds API v4 |
| --- | --- | --- |
| Domain | football-specific entity graph | multi-sport compact event graph |
| Incremental odds | fixed last-10-seconds endpoints | full/current polling; bookmaker/market update times |
| Documented freshness | in-play generally 2-10 seconds; poll latest at 10 seconds | featured odds roughly 40-60 seconds, exchanges faster |
| History | Standard retains latest only; Premium history is separate | paid historical snapshots from June 2020 |
| Quota shape | requests per entity per hour; every page counts | monthly credits; odds cost is markets x regions |
| Authentication | query token documented; header docs are inconsistent | `apiKey` query parameter documented |
| Key risk | exact Standard/Premium entitlement and retention rights | quota multiplication and query-key URL exposure |

## Approval record required before source policy changes

The commercial/legal owner must record written answers for:

- exact leagues, bookmakers and markets in the purchased entitlement;
- indefinite raw snapshot retention and post-subscription retention;
- predictive-model training and derived probability/value/ticket analytics;
- authenticated/public display of individual bookmaker prices;
- whether alerts, comparison, export or download are redistribution;
- multi-domain/API/mobile deployment pricing;
- attribution, trademark and bookmaker-logo restrictions;
- correction policy, SLA, support, burst and quota-exhaustion behavior;
- EU/Romanian gambling advertising, age-gating and responsible-gambling review.

Until all required fields are approved, descriptors stay
`APPROVAL_REQUIRED`, body retention is absent, credentials are not loaded, and
live canary stages remain blocked.

## Official references

- [Sportmonks authentication](https://docs.sportmonks.com/v3/welcome/authentication)
- [Sportmonks latest updated odds](https://docs.sportmonks.com/v3/endpoints-and-entities/endpoints/standard-odds-feed/pre-match-odds/get-last-updated-odds)
- [Sportmonks odd fields](https://docs.sportmonks.com/v3/endpoints-and-entities/entities/odd-and-prediction)
- [Sportmonks pricing](https://www.sportmonks.com/football-api/plans-pricing/)
- [Sportmonks terms](https://www.sportmonks.com/terms-of-service/)
- [The Odds API v4](https://the-odds-api.com/liveapi/guides/v4/)
- [The Odds API update intervals](https://the-odds-api.com/sports-odds-data/update-intervals.html)
- [The Odds API terms](https://the-odds-api.com/terms-and-conditions.html)
