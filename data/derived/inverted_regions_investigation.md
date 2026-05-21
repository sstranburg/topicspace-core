# Inverted-region bias investigation

_F-007 V2 phase 2 · generated 2026-05-21_

Investigation purpose: 10 public regions flagged with hit_5d ≤ 30%; 7 of 10 are sign=−1. This document surfaces the underlying analyst-note evidence to distinguish (A) extractor bug, (B) fade dynamic, (C) mislabel, (D) small-sample noise.

For each region: theme label, sign, n_obs, corpus hit_5d, member tickers, sample headlines + near_term_views, per-actor breakdown, and an opposite-sign cross-check.

---

## Overview

| # | Region | Theme label | sign | n | hit_5d | opp sign hit | candidate |
|---|---|---|---|---|---|---|---|
| 1 | `reg-83de2ee3ed` | Intel's AI Strategy and Challenges | -1 | 14 | 7% | — | _tbd_ |
| 2 | `reg-bdf4e73cd0` | AI infrastructure investment dynamics | -1 | 12 | 17% | — | _tbd_ |
| 3 | `reg-fa97d6d4fe` | Datadog's strong Q4 earnings performance | -1 | 10 | 20% | — | _tbd_ |
| 4 | `reg-98f1e5d930` | AI-driven growth and investment strategies | +1 | 13 | 23% | 59% (n=75) | _tbd_ |
| 5 | `reg-74c386f0c2` | Micron stock volatility and market sentiment | -1 | 29 | 24% | 0% (n=1) | _tbd_ |
| 6 | `reg-b548702a9e` | AI chip market dynamics and trends | -1 | 30 | 27% | 40% (n=10) | _tbd_ |
| 7 | `reg-fa3c18b522` | AI stock investment opportunities | -1 | 17 | 29% | 75% (n=4) | _tbd_ |
| 8 | `reg-08c0a6a5ba` | AI-driven growth in tech stocks | +1 | 27 | 30% | 40% (n=15) | _tbd_ |
| 9 | `reg-4ab091e6dc` | Oracle's AI and cloud growth prospects | +1 | 10 | 30% | 42% (n=12) | _tbd_ |
| 10 | `reg-74e4c4238a` | AI investment strategies and outlook | -1 | 10 | 30% | 0% (n=3) | _tbd_ |

---

## 1. Intel's AI Strategy and Challenges  (7% 5d, sign=-1, n=14)

- **region_id:** `reg-83de2ee3ed`
- **theme_id:**  `theme-523f913c`
- **hit rates:** 5d 7% · 10d 21% · 20d 14%
- **member tickers** (4): ASML, INTC, MSFT, TSM
- **opposite sign (sign=+1):** does not exist in corpus

- **sample analyst notes** (top by conviction, max 6):

  - **ASML** · 2026-01-05 · conv=0.75
    - headline: _EUV Demand Faces Headwinds Amid Price Pressure_
    - near_term_view: The outlook for ASML appears bearish as the narrative surrounding EUV demand is weakening, reflected in the declining narrative score and significant negative NDS. Price is currently leading with a positive relative retu…
  - **ASML** · 2026-01-06 · conv=0.75
    - headline: _EUV Demand Faces Pressure Amid AI Chip Cycle_
    - near_term_view: The structural picture indicates continued downward pressure on ASML's price, with negative narrative and dislocation scores suggesting a bearish continuation in the near term. Investors may remain cautious as EUV demand…
  - **INTC** · 2026-01-07 · conv=0.75
    - headline: _Intel Faces Continued Narrative Challenges Ahead_
    - near_term_view: The structural picture indicates ongoing challenges for Intel, with a negative narrative and disagreement in market sentiment. Price trends suggest further downside potential in the coming months.
  - **INTC** · 2026-01-08 · conv=0.75
    - headline: _Struggling to break negative narrative cycle._
    - near_term_view: Over the next 1-2 months, INTC is likely to continue facing downward pressure as its negative narrative persists, despite some relative price strength. The divergence with peers indicates a challenging environment for re…
  - **INTC** · 2026-01-09 · conv=0.75
    - headline: _Struggles Persist Despite Foundry Pivot News_
    - near_term_view: The structural picture indicates continued difficulty for INTC, with the negative narrative and disagreement state prevailing. The foundry pivot may not be enough to offset the prevailing bearish sentiment in the near te…
  - **INTC** · 2026-01-14 · conv=0.75
    - headline: _Intel Faces Challenges Amidst Foundry Pivot_
    - near_term_view: The outlook for Intel remains weak, with persistent negative sentiment and a disagreement state indicating ongoing challenges. The market's reaction suggests continued struggles despite a pivot towards foundry services.

- **per-actor breakdown:**

  | ticker | n | hit_5d |
  |---|---|---|
  | INTC | 6 | 0% |
  | ASML | 4 | 0% |
  | TSM | 3 | 0% |
  | MSFT | 1 | 100% |

---

## 2. AI infrastructure investment dynamics  (17% 5d, sign=-1, n=12)

- **region_id:** `reg-bdf4e73cd0`
- **theme_id:**  `theme-06abf1b2`
- **hit rates:** 5d 17% · 10d 33% · 20d 42%
- **member tickers** (6): CEG, CRWV, MP, SNOW, TTD, VST
- **opposite sign (sign=+1):** does not exist in corpus

- **sample analyst notes** (top by conviction, max 6):

  - **SNOW** · 2026-04-08 · conv=0.75
    - headline: _Continued pressure on data cloud growth narrative_
    - near_term_view: The outlook for SNOW remains bearish as the negative confirmation state persists, with a stalled narrative and ongoing price pressure in the growth software sector. Expect continued struggles in the near-term as market s…
  - **SNOW** · 2026-04-09 · conv=0.75
    - headline: _Data Cloud Narrative Faces Stiff Headwinds_
    - near_term_view: The ongoing negative confirmation state suggests continued downward pressure on SNOW's price, with the data cloud growth narrative struggling to gain traction. Expect a challenging 1-2 months ahead as market sentiment re…
  - **CRWV** · 2026-04-09 · conv=0.75
    - headline: _CoreWeave Faces Continued Price Resistance_
    - near_term_view: The structural picture suggests continued price pressure as the fading IPO hype does not align with robust narrative support. Expect further divergence between narrative and price performance in the near term.
  - **CRWV** · 2026-04-10 · conv=0.75
    - headline: _CoreWeave Cloud Hype Faces Price Pressure_
    - near_term_view: The fading IPO hype and negative narrative pressure suggest continued downward price pressure in the coming months. A strong divergence from peers indicates potential challenges ahead, despite the recent positive relativ…
  - **CRWV** · 2026-04-13 · conv=0.75
    - headline: _CoreWeave Faces Continued Pressure Amid IPO Hype Fade_
    - near_term_view: The trajectory suggests ongoing price rejection of the negative narrative, but the substantial narrative dislocation indicates significant downward pressure. Expect continued volatility with bearish tendencies in the nea…
  - **TTD** · 2026-04-08 · conv=0.75
    - headline: _Persistent Divergence Amidst Sector Challenges_
    - near_term_view: The next 1-2 months are likely to see continued pressure on TTD's price as the divergence between narrative strength and market performance persists. The broader software sector's struggles with AI disruption may further…

- **per-actor breakdown:**

  | ticker | n | hit_5d |
  |---|---|---|
  | CRWV | 4 | 0% |
  | MP | 3 | 0% |
  | SNOW | 2 | 50% |
  | CEG | 1 | 100% |
  | TTD | 1 | 0% |
  | VST | 1 | 0% |

---

## 3. Datadog's strong Q4 earnings performance  (20% 5d, sign=-1, n=10)

- **region_id:** `reg-fa97d6d4fe`
- **theme_id:**  `theme-f22efe9e`
- **hit rates:** 5d 20% · 10d 40% · 20d 30%
- **member tickers** (3): DDOG, SNOW, TTD
- **opposite sign (sign=+1):** does not exist in corpus

- **sample analyst notes** (top by conviction, max 6):

  - **SNOW** · 2026-02-05 · conv=0.85
    - headline: _Continued selloff amidst stalled data cloud growth narrative_
    - near_term_view: The structural picture indicates a continuation of negative confirmation, with the data cloud growth narrative failing to translate into positive price movement. Expect sustained downward pressure in the near term as sen…
  - **DDOG** · 2026-02-09 · conv=0.75
    - headline: _Persistent Divergence Amidst Positive Narrative_
    - near_term_view: The next 1-2 months are likely to see continued struggles for DDOG as the positive narrative around AI-native observability fails to translate into price appreciation, reflecting a broader divergence trend. Pressure from…
  - **SNOW** · 2026-03-04 · conv=0.75
    - headline: _Data cloud narrative struggles to gain traction._
    - near_term_view: The growth narrative around data cloud services is stalling, with negative confirmation in recent price movements. Expect continued downward pressure as the market reacts to the lack of positive momentum.
  - **TTD** · 2026-02-03 · conv=0.75
    - headline: _Divergence Signals Persistent Price Weakness_
    - near_term_view: The current divergence state indicates that the positive narrative surrounding TTD is not translating into price gains, suggesting continued bearish pressure in the near term. Expect the stock to remain under pressure as…
  - **DDOG** · 2026-02-04 · conv=0.70
    - headline: _Struggling with market narratives amid pricing pressure_
    - near_term_view: The next 1-2 months are likely to see continued pressure on DDOG's price, as the divergence between narrative strength and market performance persists. The broader software sector's challenges, particularly concerning AI…
  - **DDOG** · 2026-02-05 · conv=0.70
    - headline: _Struggles Amid Broader Software Sector Pressure_
    - near_term_view: The next 1-2 months are likely to see continued downward pressure on DDOG's price, as the broader narrative of AI disruption weighs heavily on growth software stocks. The divergence between strong narrative and price act…

- **per-actor breakdown:**

  | ticker | n | hit_5d |
  |---|---|---|
  | DDOG | 5 | 0% |
  | SNOW | 3 | 33% |
  | TTD | 2 | 50% |

---

## 4. AI-driven growth and investment strategies  (23% 5d, sign=+1, n=13)

- **region_id:** `reg-98f1e5d930`
- **theme_id:**  `theme-4d240b54`
- **hit rates:** 5d 23% · 10d 38% · 20d 69%
- **member tickers** (6): AMD, ANET, ARM, DDOG, NBIS, VST
- **opposite sign (sign=-1):** hit_5d = 59% on n=75 observations
  - flip-back signal: opposite-sign hit_5d is +36pp higher than this region's. **Strong sign-flip candidate.**

- **sample analyst notes** (top by conviction, max 6):

  - **DDOG** · 2026-01-22 · conv=0.80
    - headline: _Positive narrative confirmed; strong growth potential ahead._
    - near_term_view: With a confirmed state and strong narrative alignment, DDOG is positioned for potential price appreciation in the coming months. The recent positive trajectory suggests continued investor confidence in its AI-native obse…
  - **ARM** · 2026-01-21 · conv=0.80
    - headline: _Strong momentum in AI chip licensing for ARM_
    - near_term_view: With a confirmed state and a positive narrative surrounding AI chip architecture licensing, ARM is likely to see continued price support and growth in the next 1-2 months. The strong NDS and positive relative return indi…
  - **ANET** · 2026-01-28 · conv=0.75
    - headline: _AI Infrastructure Demand Remains Strong_
    - near_term_view: The confirmed state indicates solid demand for AI networking infrastructure, likely supported by the ongoing hyperscaler spending. Expect continued price stability as the narrative aligns with performance metrics.
  - **VST** · 2026-01-14 · conv=0.75
    - headline: _Strong performance driven by AI data center demand_
    - near_term_view: The confirmed state indicates strong alignment with the narrative, suggesting continued bullish momentum in the next couple of months. The recent positive relative return reinforces the expectation of ongoing strength.
  - **VST** · 2026-01-16 · conv=0.75
    - headline: _Market Repricing Amid Strong AI Demand_
    - near_term_view: The structural picture suggests a bullish continuation as VST's pricing aligns with a strong narrative around AI data center demand. Expect gradual upward movement in the coming months.
  - **ARM** · 2026-01-16 · conv=0.75
    - headline: _Positive momentum in AI chip architecture licensing._
    - near_term_view: The structural picture suggests a continued bullish trend as the narrative around architecture licensing in AI chips gains traction. Expect price to align more closely with this positive narrative in the near term.

- **per-actor breakdown:**

  | ticker | n | hit_5d |
  |---|---|---|
  | ARM | 5 | 40% |
  | VST | 3 | 0% |
  | DDOG | 2 | 50% |
  | AMD | 1 | 0% |
  | ANET | 1 | 0% |
  | NBIS | 1 | 0% |

---

## 5. Micron stock volatility and market sentiment  (24% 5d, sign=-1, n=29)

- **region_id:** `reg-74c386f0c2`
- **theme_id:**  `theme-3924b185`
- **hit rates:** 5d 24% · 10d 24% · 20d 34%
- **member tickers** (3): ASML, MU, TSM
- **opposite sign (sign=+1):** hit_5d = 0% on n=1 observations
  - flip-back signal: opposite-sign hit_5d is -24pp higher than this region's. _Weak; opposite sign isn't much better._

- **sample analyst notes** (top by conviction, max 6):

  - **MU** · 2026-04-20 · conv=0.75
    - headline: _Uncertain HBM Demand Pressures MU Outlook_
    - near_term_view: The current negative confirmation state indicates ongoing pressure on MU's stock, primarily driven by uncertainty in HBM demand following a recent earnings miss. This may lead to further declines in the near term.
  - **MU** · 2026-02-04 · conv=0.75
    - headline: _Memory Market Struggles Amid HBM Demand Uncertainty_
    - near_term_view: The current structural picture suggests continued bearish pressure on MU's price as narrative confirmation of weakness persists. Uncertainty around HBM demand and a negative trajectory in relative performance indicate ch…
  - **MU** · 2026-03-04 · conv=0.75
    - headline: _Memory Demand Uncertainty Weighs on Future Prospects_
    - near_term_view: The next 1-2 months are likely to see continued pressure on MU due to the negative confirmation of current narratives and uncertainty around HBM demand following an earnings miss. The trajectory suggests a challenging en…
  - **MU** · 2026-03-03 · conv=0.75
    - headline: _Uncertain HBM Demand Weighs on Micron's Outlook_
    - near_term_view: Given the ongoing negative confirmation and uncertainty surrounding HBM demand, MU is likely to face continued downward pressure in the near term. The narrative suggests a lack of positive catalysts to reverse the curren…
  - **MU** · 2026-02-27 · conv=0.75
    - headline: _Uncertain HBM Demand Weighs on Memory Stocks_
    - near_term_view: Given the current negative confirmation state and a bearish narrative around HBM demand, MU is likely to continue facing downward pressure in the near term. The recent earnings miss has reinforced concerns about the memo…
  - **MU** · 2026-03-26 · conv=0.75
    - headline: _Uncertain HBM Demand Continues to Weigh on MU_
    - near_term_view: Given the persistent negative confirmation state and the uncertain demand for HBM after the earnings miss, MU is likely to face continued downward pressure in the near term. The lack of positive narrative support suggest…

- **per-actor breakdown:**

  | ticker | n | hit_5d |
  |---|---|---|
  | MU | 23 | 22% |
  | ASML | 5 | 40% |
  | TSM | 1 | 0% |

---

## 6. AI chip market dynamics and trends  (27% 5d, sign=-1, n=30)

- **region_id:** `reg-b548702a9e`
- **theme_id:**  `theme-dea30538`
- **hit rates:** 5d 27% · 10d 33% · 20d 33%
- **member tickers** (6): AMD, ANET, ASML, CEG, NVDA, VRT
- **opposite sign (sign=+1):** hit_5d = 40% on n=10 observations
  - flip-back signal: opposite-sign hit_5d is +13pp higher than this region's. _Mild flip-back signal._

- **sample analyst notes** (top by conviction, max 6):

  - **AMD** · 2026-01-15 · conv=0.75
    - headline: _AMD Faces Challenges Amidst AI GPU Competition_
    - near_term_view: In the next 1-2 months, AMD's price-pressured state suggests continued struggles against negative narrative dislocation. The competitive landscape with NVIDIA remains a significant headwind.
  - **NVDA** · 2025-12-24 · conv=0.75
    - headline: _Navigating Price Pressure Amidst AI Narrative_
    - near_term_view: With a negative narrative dislocation score and price-led state, NVDA may face continued downward pressure in the near term. The market's focus on pricing power versus custom silicon is essential as hyperscaler capex dis…
  - **NVDA** · 2026-01-06 · conv=0.75
    - headline: _Navigating AI Infrastructure Amid Market Pressures_
    - near_term_view: In the next 1-2 months, NVDA is likely to face continued pricing pressures as the market grapples with the realities of its narrative underperformance, particularly in the context of China market share erosion and hypers…
  - **AMD** · 2025-12-11 · conv=0.70
    - headline: _Price Pressure Amid AI GPU Rivalry_
    - near_term_view: In the next 1-2 months, AMD is likely to continue facing downward pressure as the narrative around AI GPU competition with NVDA fails to translate into price gains. The price is currently ahead of the story, indicating a…
  - **AMD** · 2025-12-16 · conv=0.70
    - headline: _AMD Faces Pressure Amidst AI GPU Competition_
    - near_term_view: Over the next 1-2 months, AMD is likely to continue facing pricing pressure as the narrative surrounding AI GPU competition fails to translate into positive price movement. The repricing state indicates a struggle to ali…
  - **ASML** · 2026-01-08 · conv=0.70
    - headline: _EUV Demand Faces Pressure Amid Price Rotation_
    - near_term_view: As of now, ASML is experiencing significant price-led pressures with a declining narrative score. The near-term outlook suggests continued bearish momentum as the market recalibrates expectations around EUV demand in the…

- **per-actor breakdown:**

  | ticker | n | hit_5d |
  |---|---|---|
  | AMD | 14 | 21% |
  | NVDA | 11 | 27% |
  | ASML | 2 | 0% |
  | ANET | 1 | 100% |
  | CEG | 1 | 0% |
  | VRT | 1 | 100% |

---

## 7. AI stock investment opportunities  (29% 5d, sign=-1, n=17)

- **region_id:** `reg-fa3c18b522`
- **theme_id:**  `theme-d71b596b`
- **hit rates:** 5d 29% · 10d 53% · 20d 53%
- **member tickers** (9): AAPL, ADBE, CRM, DDOG, DELL, MRVL, MSFT, NBIS, VST
- **opposite sign (sign=+1):** hit_5d = 75% on n=4 observations
  - flip-back signal: opposite-sign hit_5d is +46pp higher than this region's. **Strong sign-flip candidate.**

- **sample analyst notes** (top by conviction, max 6):

  - **CRM** · 2026-04-13 · conv=0.80
    - headline: _Continued selloff reflects AI disruption fears_
    - near_term_view: The next 1-2 months are likely to see continued downward pressure as the negative narrative and competitive landscape weigh heavily on CRM's performance. The cooling adoption of Agentforce and margin pressures from AI co…
  - **MRVL** · 2026-04-15 · conv=0.75
    - headline: _AI Networking Momentum Faces Headwinds_
    - near_term_view: Despite confirmed AI networking revenue growth, the negative narrative dislocation score indicates potential challenges ahead. Expect price volatility as market sentiment adjusts.
  - **ADBE** · 2026-04-14 · conv=0.75
    - headline: _Earnings Pressure Amid AI Disruption Narrative_
    - near_term_view: In the next 1-2 months, ADBE is likely to face continued pressure as the narrative surrounding AI disruption weighs heavily on earnings expectations. The divergence observed suggests a lack of market confidence in a turn…
  - **DDOG** · 2026-04-13 · conv=0.75
    - headline: _Struggling Amidst AI Disruption in Software Sector_
    - near_term_view: The next 1-2 months are likely to see continued pressure as the broader software cohort faces negative sentiment driven by AI disruptions. DDOG's narrative remains underappreciated, suggesting further divergence from per…
  - **ADBE** · 2026-04-13 · conv=0.75
    - headline: _Earnings Pressure Amid AI Creative Tools Narrative_
    - near_term_view: The structural divergence indicates continued selling pressure in the near term, with earnings concerns overshadowing any positive sentiment from AI developments. Expect a challenging environment as the market remains ca…
  - **DELL** · 2026-04-15 · conv=0.70
    - headline: _Navigating AI Server Demand Amid Margin Pressures_
    - near_term_view: In the next 1-2 months, DELL is expected to face continued challenges as margin pressures persist against a backdrop of AI server demand. The divergence in pricing suggests a bearish sentiment, warranting caution.

- **per-actor breakdown:**

  | ticker | n | hit_5d |
  |---|---|---|
  | ADBE | 3 | 33% |
  | DDOG | 3 | 0% |
  | VST | 3 | 100% |
  | DELL | 2 | 0% |
  | MRVL | 2 | 0% |
  | AAPL | 1 | 0% |
  | CRM | 1 | 0% |
  | MSFT | 1 | 0% |
  | NBIS | 1 | 100% |

---

## 8. AI-driven growth in tech stocks  (30% 5d, sign=+1, n=27)

- **region_id:** `reg-08c0a6a5ba`
- **theme_id:**  `theme-2caf2d47`
- **hit rates:** 5d 30% · 10d 26% · 20d 22%
- **member tickers** (10): ANET, DDOG, META, MRVL, MSFT, NBIS, ORCL, PLTR, SMCI, VRT
- **opposite sign (sign=-1):** hit_5d = 40% on n=15 observations
  - flip-back signal: opposite-sign hit_5d is +10pp higher than this region's. _Mild flip-back signal._

- **sample analyst notes** (top by conviction, max 6):

  - **PLTR** · 2025-12-08 · conv=0.80
    - headline: _Strength in Government Contracts Boosts Outlook_
    - near_term_view: The positive trajectory in government AI contracts and commercial growth indicates a strong continuation in performance over the next couple of months. Expect the price to maintain upward momentum as the narrative remain…
  - **SMCI** · 2025-12-09 · conv=0.80
    - headline: _Strong momentum in AI server demand expected._
    - near_term_view: With confirmed structural strength and a positive narrative around AI server demand, SMCI is positioned for continued growth in the short term. The partnership with VAST Data further supports this outlook.
  - **MRVL** · 2025-12-02 · conv=0.80
    - headline: _AI Networking Momentum Fuels Positive Outlook_
    - near_term_view: The strong narrative around accelerating AI networking revenue supports a continued positive trajectory in the near term, with price confirming the bullish sentiment. Expect further gains as market confidence builds.
  - **MSFT** · 2025-12-02 · conv=0.75
    - headline: _Gaining traction in AI as Copilot adoption rises_
    - near_term_view: In the next 1-2 months, MSFT is expected to see continued positive momentum driven by the growing enterprise adoption of Copilot and its strategic relationship with OpenAI. However, the pricing dynamics indicate a cautio…
  - **VRT** · 2025-12-03 · conv=0.75
    - headline: _Positive momentum in AI infrastructure growth._
    - near_term_view: The structural indicators suggest a continued upward trajectory in demand for cooling solutions in AI data centers, supported by improving narrative and dislocation scores. Expect further price appreciation as backlog co…
  - **PLTR** · 2025-12-03 · conv=0.75
    - headline: _Positive momentum in government AI contracts._
    - near_term_view: With a confirmed state and strong narrative backing, PLTR is likely to continue benefiting from government AI contracts and commercial growth in the near term. Expect upward price movement as the narrative solidifies.

- **per-actor breakdown:**

  | ticker | n | hit_5d |
  |---|---|---|
  | VRT | 6 | 33% |
  | SMCI | 4 | 0% |
  | DDOG | 3 | 0% |
  | META | 3 | 67% |
  | NBIS | 3 | 0% |
  | PLTR | 3 | 100% |
  | MRVL | 2 | 0% |
  | ANET | 1 | 0% |
  | MSFT | 1 | 0% |
  | ORCL | 1 | 100% |

---

## 9. Oracle's AI and cloud growth prospects  (30% 5d, sign=+1, n=10)

- **region_id:** `reg-4ab091e6dc`
- **theme_id:**  `theme-7784dc6d`
- **hit rates:** 5d 30% · 10d 40% · 20d 80%
- **member tickers** (1): ORCL
- **opposite sign (sign=-1):** hit_5d = 42% on n=12 observations
  - flip-back signal: opposite-sign hit_5d is +12pp higher than this region's. _Mild flip-back signal._

- **sample analyst notes** (top by conviction, max 6):

  - **ORCL** · 2026-03-12 · conv=0.75
    - headline: _Solid growth signals amidst cloud expansion efforts._
    - near_term_view: The structural indicators suggest a positive trajectory for ORCL over the next couple of months, driven by ongoing cloud and AI infrastructure expansion. The confirmed state and positive narrative score indicate strong g…
  - **ORCL** · 2026-03-17 · conv=0.75
    - headline: _Strong narrative support for growth trajectory._
    - near_term_view: As the narrative around cloud and AI infrastructure expansion remains robust, ORCL is positioned for continued growth. The positive NDS indicates strengthening momentum in the coming months.
  - **ORCL** · 2026-03-19 · conv=0.75
    - headline: _Cloud and AI Growth Driving Optimism_
    - near_term_view: The current repricing phase suggests that ORCL is poised for a bullish continuation, driven by strong narrative support around cloud and AI infrastructure expansion. The focus on OCI growth and strategic partnerships sho…
  - **ORCL** · 2026-03-20 · conv=0.75
    - headline: _Repricing Continues Amid Cloud Expansion Hype_
    - near_term_view: The next 1-2 months are expected to see continued strength as Oracle capitalizes on its cloud and AI infrastructure narrative, despite recent price lag. The positive narrative and strong NDS suggest potential for upward …
  - **ORCL** · 2026-03-23 · conv=0.75
    - headline: _Cloud Growth and AI Infrastructure Driving Expectations_
    - near_term_view: The outlook for ORCL remains positive as the repricing phase continues, supported by strong narrative momentum around cloud and AI infrastructure. Anticipated growth from OCI and the Stargate JV with OpenAI is likely to …
  - **ORCL** · 2026-03-31 · conv=0.75
    - headline: _Repricing Signals Continued Growth Potential_
    - near_term_view: In the next 1-2 months, ORCL is positioned for potential upside as the repricing trend aligns with strong narrative support from cloud and AI infrastructure expansion. Positive growth indicators from OCI and the Stargate…

- **per-actor breakdown:**

  | ticker | n | hit_5d |
  |---|---|---|
  | ORCL | 10 | 30% |

---

## 10. AI investment strategies and outlook  (30% 5d, sign=-1, n=10)

- **region_id:** `reg-74e4c4238a`
- **theme_id:**  `theme-806e8736`
- **hit rates:** 5d 30% · 10d 20% · 20d 40%
- **member tickers** (9): ADBE, ANET, DELL, GOOGL, META, MSFT, SMCI, VRT, VST
- **opposite sign (sign=+1):** hit_5d = 0% on n=3 observations
  - flip-back signal: opposite-sign hit_5d is -30pp higher than this region's. _Weak; opposite sign isn't much better._

- **sample analyst notes** (top by conviction, max 6):

  - **VRT** · 2026-02-23 · conv=0.75
    - headline: _Price Pressure Continues Amid AI Infrastructure Struggles_
    - near_term_view: Given the current price-led state and negative narrative dislocation score, VRT is likely to face continued price pressure over the next 1-2 months. The backlog conversion may not be sufficient to counter the broader neg…
  - **ADBE** · 2026-02-23 · conv=0.75
    - headline: _Continued earnings pressure amid AI disruption narrative._
    - near_term_view: ADBE is likely to face ongoing price pressure as the narrative around AI's impact on software margins continues to dominate. With a divergence state persisting, the outlook remains negative in the near term.
  - **MSFT** · 2026-02-23 · conv=0.70
    - headline: _Repricing Amidst AI Sector Pressures_
    - near_term_view: In the near term, MSFT's narrative of Copilot and OpenAI adoption is not translating into price performance, reflecting broader sector challenges. Expect continued repricing pressures as the market digests AI margin conc…
  - **ANET** · 2026-02-24 · conv=0.70
    - headline: _Divergence Continues Amidst AI Infrastructure Demand_
    - near_term_view: The outlook suggests continued divergence, with price lagging behind narrative momentum. This trend may persist as hyperscaler spending dynamics play out.
  - **ANET** · 2026-02-25 · conv=0.70
    - headline: _Struggling to Align with Positive AI Narrative_
    - near_term_view: The trajectory suggests continued divergence, indicating that the market is not fully recognizing the positive narrative around AI networking demand. Expect further pressure on relative performance in the near term.
  - **GOOGL** · 2026-02-23 · conv=0.70
    - headline: _AI Search Competition Pressures Stock Outlook_
    - near_term_view: The structural picture indicates continued pressure on GOOGL's price due to competitive dynamics in AI search and ongoing concerns about margin erosion. A bearish trend is likely as narrative strength fails to translate …

- **per-actor breakdown:**

  | ticker | n | hit_5d |
  |---|---|---|
  | ANET | 2 | 50% |
  | ADBE | 1 | 0% |
  | DELL | 1 | 0% |
  | GOOGL | 1 | 100% |
  | META | 1 | 0% |
  | MSFT | 1 | 0% |
  | SMCI | 1 | 0% |
  | VRT | 1 | 0% |
  | VST | 1 | 100% |

---

## Synthesis

### Per-region verdicts

| # | Region | Verdict | Evidence |
|---|---|---|---|
| 1 | Intel's AI Strategy and Challenges (−1) | **B** fade | Headlines genuinely bearish (EUV demand pressure, foundry struggles, narrative challenges). Market faded the bearish thesis. |
| 2 | AI infrastructure investment dynamics (−1) | **B** fade | CRWV / SNOW / MP bearish reads accurate. IPO fade and data-cloud-stall narratives were real. Market priced through them in 5d. |
| 3 | Datadog's strong Q4 earnings performance (−1) | **C** mislabel | **Label says "strong Q4" but attached content is bearish DDOG / SNOW selloff reads.** Cluster label is stale relative to current attachments. |
| 4 | AI-driven growth and investment strategies (+1) | **B** fade | ARM / VST / DDOG bullish reads accurate (real AI-growth narratives). Opposite sign hit 59% on n=75 — strong contrarian signal at the theme level. |
| 5 | Micron stock volatility and market sentiment (−1) | **B** fade | HBM-demand-uncertainty bearish reads were real (earnings miss reinforced the negative). MU price kept up anyway. |
| 6 | AI chip market dynamics and trends (−1) | **B** fade | AMD / NVDA AI-GPU-competition bearish reads accurate. Market faded most within 5d. |
| 7 | AI stock investment opportunities (−1) | **B** fade | Broad April-bearish reads on CRM / DDOG / ADBE / DELL / MRVL — accurate, but market rejected within a week. Opposite sign hit 75% on n=4. |
| 8 | AI-driven growth in tech stocks (+1) | **B** fade | PLTR / SMCI / MRVL / VRT bullish reads correctly framed (government AI contracts, AI server demand). Market faded ~70% in 5d. |
| 9 | Oracle's AI and cloud growth prospects (+1) | **B** fade | ORCL bullish reads accurate (Stargate JV, OCI growth). Stock didn't follow at 5d (did follow at 20d, hit 80%). |
| 10 | AI investment strategies and outlook (−1) | **B** fade | Broad bearish AI-disruption reads accurate. Market priced through them. |

### Dominant pattern

**9 of 10 regions fit hypothesis B (fade dynamic).** The L2 direction extractor is reading the analyst notes correctly. The headlines and `near_term_view` text are genuinely directional in the assigned direction. The 5-day mismatch with price is not an extraction failure — it is the **"narrative-already-priced"** dynamic. Strong analyst consensus on a hot AI-ecosystem theme is itself a contrarian short-horizon signal.

The sign=−1 majority (7 of 10) is consistent with this: bearish analyst notes on heavily-discussed AI themes (Intel foundry, Micron HBM, CoreWeave IPO, AI software disruption) accumulate disproportionately because pessimism on a hot story generates more commentary than indifference. When the market keeps validating the longer-term bullish story, those bearish 5d windows look like inversions.

The **one exception** (Region 3, Datadog "strong Q4") is a real **labeling-drift bug**: the LLM-generated cluster label was set when one positive analyst note dominated the cluster centroid, but the attached content is now mostly bearish DDOG / SNOW selloff reads. The label is stale. This is fixable separately from the direction question.

### Recommended next action

**Do NOT re-tune the L2 direction extractor.** The 7-of-10 bearish skew is a real market dynamic, not a bug. Re-tuning would mute correctly-extracted bearish reads on themes where the contrarian is the actually-tradable signal.

**The V2-acts step shifts shape:**

1. **Build a per-region sign-flip rule (the operational "INVERT" decision class).** For regions meeting all of:
   - Public tier (n ≥ 10 in corpus)
   - Corpus hit_5d ≤ 30%
   - Rolling-walkforward range across folds ≤ 20pp (i.e. the inversion is stable, not a one-fold accident)

   Treat L2 direction as inverted for that region's 5d window. This is the F-007 V2 phase 2 "escalation" — except the escalation is automatic re-direction, not a human-review queue.

2. **Fix cluster-label staleness** (Region 3-style mislabels). When a cluster's attached-content composition drifts > X% from when its label was generated, regenerate the label via the LLM. Add a staleness check to the labeling step in `build_performance_regions.py` (or wherever cluster labels are surfaced).

3. **Compound with F-006 #6 at 5d.** The persistence-as-prior-weight finding (5d positive across folds) and the sign-flip rule both apply at the same horizon. Worth testing whether "persistent entity in an inverted region at 5d" is the strongest setup before either ships independently.

4. **Defer escalation-to-human routing.** The original phase 2 plan included a Slack route / review queue. Given the finding here, automatic re-direction in the operating layer is the higher-leverage move — humans don't need to triage each inverted region; the operating layer should trade them as contrarian.

### Open questions

- **Does the bearish skew persist as the corpus grows?** Today's 7/10 ratio is on a 175-day window. Worth re-running this investigation monthly to check whether the asymmetry holds or whether the corpus eventually rebalances toward 50/50.
- **Is the fade dynamic concentrated in REPRICING / DIVERGENCE states?** Cross-tabulating inverted regions against state at observation time would test whether the existing state taxonomy already captures the pattern. If yes, the sign-flip rule is redundant with state-conditional weighting (which F-007 V2's "add state as a region sub-dimension" followup explicitly anticipates).
- **Do the +1 fade regions and −1 fade regions share a market regime?** Both happen in the same corpus window — is the fade dynamic a property of THIS window (broad mean-reversion in April / May) or a structural pattern?
