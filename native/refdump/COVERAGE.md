# Feature coverage of the 65 public scenarios

This file was built from `regression_suite/scenarios/*.json`, the adapter (`abides_fork/config.py`,
`agents.py`, `trace.py`) and the patched ABIDES in `agenthon-track3:cand2`. The message and
event statistics in sections 3 and 4 come from the dumps actually produced in `runs/`:
s001_price_time_priority, fastlob_core, mp01_stp_newest_baseline, ra01_fundamental_shock_mid,
eq_lognormal_highsigma and as06_throughput_fast.

## 1. Scenario to engine mapping (what the reference actually consumes)

**Consumed:**
* `seed`
* `horizon_ns`: `mkt_close = mkt_open + horizon_ns`, and `stop_time = mkt_close + 1s`.
  `mkt_open` is 2021-02-05 09:30:00 = 1612517400000000000. Kernel `start_time` is midnight,
  1612483200000000000.
* `agent_configs`, in list order. Agent ids run 1..N in that order. Id 0 is the exchange.
* `oracle_config.params` fields `initial_price`, `kappa`, `sigma`, `jump_intensity`,
  `jump_sigma` and `scheduled_jump`.
* `latency_config`.
* `exchange_config` fields `protocol_enforcement`, `stp_policy`, `ack_delay_ns` and
  `compute_delay_ns`.

**Ignored by the reference (a port must ignore them too):**
* `agent_mix`: it disagrees with `agent_configs` in gb_highfreq_40hz_60s, ra05 and ra06, and
  is absent in mp01..07.
* `exchange_config` fields `symbol` (the book is always `ABM`), `tick_size`, `lot_size`,
  `min_price`, `max_price` and `order_types_allowed`.
* `oracle_config.type`, `dt_ns` and `noise_type`.
* `latency_config.params` fields `scale_ns`, `sigma` for non-lognormal models, and `mean_ns`
  for uniform and pareto.
* `ValueTrader.fundamental_value_source`.
* `output_config` and `tolerance`.

| Feature | Reference behaviour |
|---|---|
| Latency `log_normal` | `latency.lognormal(mean=ln(mean_ns), sigma)`, clamped to `[min_ns,max_ns]`, then `int(round(x))` (Python round is half-to-even). One draw per send with `sender != recipient`. A self-send gets 0 and makes **no draw**. |
| Latency `uniform` | `latency.uniform(min_ns, max_ns)`, then clamp and round. |
| Latency `pareto` | `(min_ns>0 ? min_ns : 1) * (1 + latency.pareto(alpha))`. `alpha` defaults to 1.5. Then clamp and round. |
| Latency `deterministic` | Constant `mean_ns`, clamped. **No RNG draw.** |
| Oracle kappa and sigma | `kappa/1e9` per ns if > 0, else 1.67e-16. `fund_vol = sigma` (default 5e-5), `sigma_s = 0`, `r_bar = initial_price`. |
| Oracle megashocks | `lambda = jump_intensity/1e9` per ns if > 0, else 2.77778e-18 (never fires within a horizon). `megashock_mean = jump_sigma or 1000.0`, `megashock_var = 50000`. Inter-arrival times come from the **global** `np.random.exponential`. The value comes from `oracle.normal`, and the sign from `oracle.randint(2)`. The init draw happens even with jumps "off". The first megashock time is a float (`mkt_open + exponential`); later ones are int. |
| Oracle scheduled_jump (patch) | Absolute time `mkt_open + time_ns`. The magnitude is added once, deterministically, to the first OU value computed at `ts >= time`. No RNG. |
| Exchange `protocol_enforcement` | True only in MP. Without it, `stp_policy` is **ignored** (None), even though every scenario lists one. With it, `cancel_newest` cancels the aggressor remainder (sends OrderCancelledMsg), and `cancel_oldest` cancels the resting same-agent order and retries the match. |
| `ack_delay_ns` / `compute_delay_ns` | **No public scenario sets them.** Exchange `pipeline_delay = computation_delay = 0` everywhere. Agents get `default_computation_delay = 50` ns. |
| Wake schedule | `interval = rebalance_interval_ns`, or `int(1e9/arrival_rate_hz)`. The first wakeup is at kernel start and sends MarketClosePriceRequest and MarketHoursRequest. MarketHoursMsg then sets a wakeup at `mkt_open`. From then on, every wake re-arms `t+interval` and sends `QuerySpreadMsg(depth=1)`, and `act()` runs on the response. |
| NoiseTrader | `normal(mean,std)` for size, then `randint(0,2)` for the side, then `randint(0,offset+1)`. Anchors on the touch, or on `initial_price` when the book is empty. |
| MarketMaker | `cancel_all_orders()` (one CancelOrderMsg per open order), then `depth_levels` BID/ASK pairs at `mid -/+ (max(2,spread)//2 + lvl)`. No RNG. |
| ValueTrader | `oracle.observe_price(sigma_n=1000)`: advances the OU (`F` records), then makes one own-stream `normal(r_t, sqrt(1000))` draw. It returns early without any draw if the book is empty. |
| MomentumTrader | No RNG. Compares against the mid `lookback` wakes ago. |

## 2. Per-scenario feature map

Families: AS/ST = agent-mix (11), CA/SF = calibration-stylized-facts (12), ME =
matching-engine-semantics (14), EQ = latency-profile (9), GB = throughput-scale (6), MP =
exchange-protocol (7), RA = reactive-agent (6).

In the tables, "legacy" means `protocol_enforcement` is unset, so STP is off. Latency is
written as `[min,max]` clamp; LN = log_normal with median and sigma.

| scenario | family | H (s) | agents (N/V/Mo/MM) | latency | kappa, sigma | jumps (lambda/s, jump_sigma) | sched. jump (t, mag) | exchange |
|---|---|---|---|---|---|---|---|---|
| as01_base_mix | AS/ST | 20 | 12/4/2/2 =20 | LN med 500, s 0.3 [100,2e+06] | 0.05, 0.001 | off | - | legacy |
| as02_scale_up_noise | AS/ST | 20 | 24/4/2/2 =32 | LN med 500, s 0.3 [100,2e+06] | 0.05, 0.001 | off | - | legacy |
| as03_mm_liquidity_heavy | AS/ST | 20 | 12/4/2/5 =23 | LN med 500, s 0.3 [100,2e+06] | 0.05, 0.001 | off | - | legacy |
| as04_value_heavy | AS/ST | 20 | 12/10/2/2 =26 | LN med 500, s 0.3 [100,2e+06] | 0.05, 0.001 | off | - | legacy |
| as05_oracle_variant | AS/ST | 20 | 12/4/2/2 =20 | LN med 500, s 0.3 [100,2e+06] | 0.5, 0.003 | off | - | legacy |
| as06_throughput_fast | AS/ST | 20 | 12/4/2/2 =20 | LN med 500, s 0.3 [100,2e+06] | 0.05, 0.001 | off | - | legacy |
| ca_baseline_calm | CA/SF | 12 | 12/4/3/2 =21 | LN med 5000, s 0.75 [100,2e+07] | 0.05, 0.001 | off | - | legacy |
| ca_fast_mean_reversion | CA/SF | 12 | 12/4/3/2 =21 | LN med 5000, s 0.75 [100,2e+07] | 0.5, 0.001 | off | - | legacy |
| ca_fat_tail_jumps | CA/SF | 12 | 12/4/3/2 =21 | LN med 5000, s 0.75 [100,2e+07] | 0.05, 0.001 | 1.5, 300.0 | - | legacy |
| ca_high_volatility | CA/SF | 12 | 12/4/3/2 =21 | LN med 5000, s 0.75 [100,2e+07] | 0.05, 0.004 | off | - | legacy |
| ca_thin_book_depth | CA/SF | 12 | 12/4/3/2 =21 | LN med 5000, s 0.75 [100,2e+07] | 0.05, 0.001 | off | - | legacy |
| cancelmodify_lifecycle | ME | 2 | 6/2/0/1 =9 | LN med 500, s 0.25 [100,2000] | 0.1, 0.001 | off | - | legacy |
| coarse_tick_ties | ME | 2.73925 | 6/2/0/1 =9 | LN med 500, s 0.25 [100,2000] | 0.1, 0.001 | off | - | legacy |
| eq001_pareto_latency_tail | EQ | 20 | 9/3/0/0 =12 | P a 1.5, min 100 [100,8e+07] | 0.05, 0.001 | off | - | legacy |
| eq_deterministic_baseline | EQ | 20 | 9/2/0/1 =12 | Det 250000 [100,5e+07] | 0.05, 0.001 | off | - | legacy |
| eq_lognormal_highmag | EQ | 20 | 9/2/0/1 =12 | LN med 2000000, s 0.75 [100,5e+08] | 0.05, 0.001 | off | - | legacy |
| eq_lognormal_highsigma | EQ | 20 | 9/2/0/1 =12 | LN med 5000, s 2.0 [100,5e+07] | 0.05, 0.001 | off | - | legacy |
| eq_lognormal_lowsigma | EQ | 20 | 9/2/0/1 =12 | LN med 5000, s 0.35 [100,5e+07] | 0.05, 0.001 | off | - | legacy |
| eq_pareto_heavytail | EQ | 20 | 9/2/0/1 =12 | P a 1.5, min 500 [500,8e+07] | 0.05, 0.001 | off | - | legacy |
| eq_uniform_tight | EQ | 20 | 9/2/0/1 =12 | U [100,2000] | 0.05, 0.001 | off | - | legacy |
| eq_uniform_wide | EQ | 20 | 9/2/0/1 =12 | U [100,2e+06] | 0.05, 0.001 | off | - | legacy |
| fastlob_core | ME | 2.81003 | 6/2/0/1 =9 | LN med 500, s 0.25 [100,2000] | 0.1, 0.001 | off | - | legacy |
| fastlob_tight_book | ME | 6.83229 | 6/2/0/1 =9 | LN med 500, s 0.25 [100,2000] | 0.1, 0.001 | off | - | legacy |
| gb_base_30agent_30s | GB | 30 | 20/6/2/2 =30 | LN med 500, s 0.5 [100,5e+06] | 0.05, 0.001 | off | - | legacy |
| gb_highfreq_40hz_60s | GB | 60 | 40/6/2/2 =50 | LN med 500, s 0.5 [100,5e+06] | 0.05, 0.001 | off | - | legacy |
| gb_horizon_240s | GB | 240 | 20/6/2/2 =30 | LN med 500, s 0.5 [100,5e+06] | 0.05, 0.001 | off | - | legacy |
| gb_mega_throughput | GB | 100 | 100/30/8/6 =144 | LN med 500, s 0.5 [100,5e+06] | 0.05, 0.001 | off | - | legacy |
| gb_pop_128_agents | GB | 30 | 90/24/8/6 =128 | LN med 500, s 0.5 [100,5e+06] | 0.05, 0.001 | off | - | legacy |
| gb_pop_horizon_scale | GB | 90 | 70/20/6/4 =100 | LN med 500, s 0.5 [100,5e+06] | 0.05, 0.001 | off | - | legacy |
| momentum_mix_priority | ME | 2.79986 | 6/2/2/1 =11 | LN med 500, s 0.25 [100,2000] | 0.1, 0.001 | off | - | legacy |
| mp01_stp_newest_baseline | MP | 3.51703 | 6/3/0/1 =10 | LN med 50000, s 0.6 [1000,2e+07] | 0.05, 0.001 | off | - | PE stp=cancel_newest |
| mp02_stp_oldest_baseline | MP | 3.51655 | 6/3/0/1 =10 | LN med 50000, s 0.6 [1000,2e+07] | 0.05, 0.001 | off | - | PE stp=cancel_oldest |
| mp03_mm_heavy_newest | MP | 2 | 6/3/0/3 =12 | LN med 50000, s 0.6 [1000,2e+07] | 0.05, 0.001 | off | - | PE stp=cancel_newest |
| mp04_mm_heavy_oldest | MP | 2 | 6/3/0/3 =12 | LN med 50000, s 0.6 [1000,2e+07] | 0.05, 0.001 | off | - | PE stp=cancel_oldest |
| mp05_cancel_churn_newest | MP | 2 | 6/3/0/1 =10 | LN med 50000, s 0.6 [1000,2e+07] | 0.05, 0.001 | off | - | PE stp=cancel_newest |
| mp06_tight_spread_selfcross | MP | 2 | 6/3/0/2 =11 | LN med 50000, s 0.6 [1000,2e+07] | 0.05, 0.001 | off | - | PE stp=cancel_newest |
| mp07_heavy_flow_oldest | MP | 3.4206 | 10/3/0/1 =14 | LN med 50000, s 0.6 [1000,2e+07] | 0.05, 0.001 | off | - | PE stp=cancel_oldest |
| mr_cancel_replace_churn | ME | 2 | 6/2/1/1 =10 | LN med 800, s 0.3 [100,1e+07] | 0.1, 0.001 | off | - | legacy |
| mr_checkpoint_cadence_fine | ME | 2 | 6/2/1/1 =10 | LN med 800, s 0.3 [100,1e+07] | 0.1, 0.001 | off | - | legacy |
| mr_deep_book_state_size | ME | 2 | 6/2/1/2 =11 | LN med 800, s 0.3 [100,1e+07] | 0.1, 0.001 | off | - | legacy |
| mr_long_horizon_replay | ME | 2 | 6/2/1/1 =10 | LN med 800, s 0.3 [100,1e+07] | 0.1, 0.001 | off | - | legacy |
| multilevel_crossing | ME | 4.62009 | 6/2/0/1 =9 | LN med 500, s 0.25 [100,2000] | 0.1, 0.001 | off | - | legacy |
| partialfill_atomicity | ME | 2.80426 | 6/2/0/1 =9 | LN med 500, s 0.25 [100,2000] | 0.1, 0.001 | off | - | legacy |
| ra01_fundamental_shock_mid | RA | 7 | 3/6/5/2 =16 | LN med 1000, s 0.5 [100,1e+07] | 0.2, 0.002 | 0.5, 200.0 | 3.5s, -20000 | legacy |
| ra02_shock_early | RA | 7 | 3/6/5/2 =16 | LN med 1000, s 0.5 [100,1e+07] | 0.2, 0.002 | 0.5, 200.0 | 2.5s, +12000 | legacy |
| ra03_large_shock | RA | 7 | 3/6/5/2 =16 | LN med 1000, s 0.5 [100,1e+07] | 0.2, 0.002 | 0.5, 200.0 | 3.5s, +30000 | legacy |
| ra04_shock_late | RA | 7 | 3/6/5/2 =16 | LN med 1000, s 0.5 [100,1e+07] | 0.2, 0.002 | 0.5, 200.0 | 4.5s, -15000 | legacy |
| ra05_shock_momentum_heavy | RA | 7 | 3/6/7/2 =18 | LN med 1000, s 0.5 [100,1e+07] | 0.2, 0.002 | 0.5, 200.0 | 3.5s, -20000 | legacy |
| ra06_shock_value_heavy | RA | 7 | 3/8/5/2 =18 | LN med 1000, s 0.5 [100,1e+07] | 0.2, 0.002 | 0.5, 200.0 | 3.5s, +18000 | legacy |
| s001_price_time_priority | ME | 10 | 3/0/0/1 =4 | U [100,2000] | 0.05, 0.0005 | off | - | legacy |
| s012_partial_fill_cancel_race | ME | 5 | 5/1/0/1 =7 | LN med 800, s 0.3 [100,1e+07] | 0.2, 0.002 | off | - | legacy |
| s019_latency_jitter_kendall | EQ | 20 | 8/2/0/0 =10 | LN med 5000, s 1.2 [100,5e+07] | 0.05, 0.001 | off | - | legacy |
| sf_01_baseline_regime | CA/SF | 2.72951 | 12/4/3/1 =20 | LN med 5000, s 0.8 [100,2e+07] | 0.05, 0.001 | 0.5, 2000.0 | - | legacy |
| sf_02_heavy_jump_tails | CA/SF | 2.72948 | 12/4/3/1 =20 | LN med 5000, s 0.8 [100,2e+07] | 0.05, 0.001 | 2.0, 5000.0 | - | legacy |
| sf_03_vol_clustering_momentum | CA/SF | 2.72632 | 12/4/6/1 =23 | LN med 5000, s 0.8 [100,2e+07] | 0.05, 0.001 | 0.5, 2000.0 | - | legacy |
| sf_04_thin_book_depth | CA/SF | 6.46095 | 12/4/3/1 =20 | LN med 5000, s 0.8 [100,2e+07] | 0.05, 0.001 | 0.5, 2000.0 | - | legacy |
| sf_05_deep_book_liquidity | CA/SF | 2 | 12/4/3/1 =20 | LN med 5000, s 0.8 [100,2e+07] | 0.05, 0.001 | 0.5, 2000.0 | - | legacy |
| sf_06_high_fundamental_vol | CA/SF | 2.72915 | 12/4/3/1 =20 | LN med 5000, s 0.8 [100,2e+07] | 0.05, 0.003 | off (js 2000.0 used as ms mean) | - | legacy |
| sf_07_coarse_agent_batch | CA/SF | 2.72358 | 6/4/3/1 =14 | LN med 5000, s 0.8 [100,2e+07] | 0.05, 0.001 | 0.5, 2000.0 | - | legacy |
| st01_liquidity_churn_baseline | AS/ST | 2.34461 | 8/3/2/1 =14 | LN med 800, s 0.3 [100,1e+07] | 0.1, 0.002 | off | - | legacy |
| st02_informed_entry_burst | AS/ST | 2.35211 | 8/6/2/1 =17 | LN med 800, s 0.3 [100,1e+07] | 0.1, 0.002 | off | - | legacy |
| st03_volatility_burst | AS/ST | 2.34608 | 8/3/2/1 =14 | LN med 800, s 0.3 [100,1e+07] | 0.03, 0.006 | off | - | legacy |
| st04_thin_book_mm_strain | AS/ST | 15 | 8/3/2/1 =14 | LN med 800, s 0.3 [100,1e+07] | 0.1, 0.002 | off | - | legacy |
| st05_latency_spike_pareto | AS/ST | 2.34238 | 8/3/2/1 =14 | P a 1.3, min 500 [500,6e+07] | 0.1, 0.002 | off | - | legacy |
| stp_cancel_newest | ME | 2.71565 | 8/2/0/1 =11 | LN med 500, s 0.25 [100,2000] | 0.1, 0.001 | off | - | legacy |

**Summary:**

* **Agent types.**
  * NoiseTrader: all 65 scenarios.
  * ValueTrader: all except s001.
  * MarketMaker: all except eq001_pareto_latency_tail and s019.
  * MomentumTrader: 40 scenarios (AS/ST, CA/SF, GB, RA, momentum_mix_priority, mr_*). It is
    absent from EQ, MP, and most of ME.
* **Latency.**
  * log_normal: 58 scenarios.
  * uniform: s001, eq_uniform_tight and eq_uniform_wide.
  * pareto: eq001, eq_pareto_heavytail and st05.
  * deterministic: only eq_deterministic_baseline.
* **Megashocks actually firing** (`jump_intensity > 0`): ca_fat_tail_jumps, sf_01..05, sf_07
  and ra01..06. sf_06 has `jump_sigma` 2000 with intensity 0, which changes only the
  never-used init megashock value.
* **Scheduled jump:** ra01..ra06.
* **STP active:** mp01..mp07. mp02, mp04 and mp07 use `cancel_oldest`; the others use
  `cancel_newest`.
* **Horizons:** 2-20 s, except GB at 30-240 s. **Agents:** 4 (s001) to 144 (gb_mega_throughput).
* **Busy-agent / requeue stress:** MarketMaker `rebalance_interval_ns` as low as 250 us (ME)
  and 500 us (MP). NoiseTrader runs at up to 40 Hz.

## 3. ABIDES message classes that flow in the produced dumps

Over the 6 dumps there were 416,392 D records: 265,730 DELIVER and 150,662 REQUEUE. The
`msg_class` spellings seen are:

`WakeupMsg`, `MarketHoursRequestMsg`, `MarketHoursMsg`, `MarketClosePriceRequestMsg`,
`MarketClosePriceMsg`, `QuerySpreadMsg`, `QuerySpreadResponseMsg`, `LimitOrderMsg`,
`CancelOrderMsg`, `OrderAcceptedMsg`, `OrderExecutedMsg`, `OrderCancelledMsg`.

These classes never occurred: `MarketClosedMsg`, `MarketOrderMsg`, `ModifyOrderMsg`,
`ReplaceOrderMsg`, `PartialCancelOrderMsg`, `OrderReplacedMsg`, `OrderModifiedMsg`,
`OrderPartialCancelledMsg`, `MessageBatch`, and every query or market-data class other than
spread. The fork agents never send them.

Kernel behaviour the port must reproduce:

* **REQUEUE is common.** It comes mostly from OrderAccepted (71k), OrderCancelled (67k) and
  OrderExecuted (13k) arriving inside an agent's 50 ns compute window. The item is re-pushed
  unchanged with priority `agent_current_times[recipient]`, and can be requeued many times.
* **Heap ties** break by `(time, sender_id, recipient_id, message_id)`.
* **Broadcast.** `MarketClosePriceMsg` is one object, so one `message_id`, sent to every
  subscriber, each with its own latency draw.

**RNG draws seen**, as `R` counts over the 6 dumps:

| Stream | Draws |
|---|---|
| `latency` lognormal | 244,988 |
| `latency` uniform | 580 |
| agent `randint` | 26,256 |
| agent `normal` | 13,756 |
| `oracle` normal | 646 |
| `oracle` randint | 12 |
| global `randint` (seed draws) | 95 |
| global `exponential` | 12 |
| global `seed` | 6 |

The exchange stream (owner `0`), `kernel` and `cfgkernel` never draw. Pareto and deterministic
latency were not among the dumped scenarios.

## 4. Agent-logged event types, and which ones trace.py consumes

**Consumed by `trace.py::extract_trace`** (the default `E` records):

| ABIDES EventType | Logged by | trace.parquet msg_type |
|---|---|---|
| `ORDER_SUBMITTED` | TradingAgent.place_limit_order | ORDER_SUBMITTED (limit price) |
| `ORDER_ACCEPTED` | TradingAgent on OrderAcceptedMsg | ORDER_ACCEPTED |
| `ORDER_EXECUTED` | TradingAgent on OrderExecutedMsg | ORDER_FILLED for the last one per order_id (in EventTime order), PARTIAL_FILL for earlier ones; fill price |
| `ORDER_CANCELLED` | TradingAgent on OrderCancelledMsg | ORDER_CANCELLED |
| `ORDER_REPLACED` | TradingAgent on OrderReplacedMsg | ORDER_REPLACED (**never occurs**) |
| `BEST_BID` / `BEST_ASK` | ExchangeAgent (via OrderBook.handle_limit_order), `"ABM,price,qty"` | QUOTE_UPDATE, keeping only the last per `(t_ns, side)`, `order_id = -1` |

`parse_logs_df` concatenates the agent logs in agent-id order. The order rows are then
stable-sorted by EventTime, and the combined frame is stable-sorted by `(t_ns, order_id)`.

`message_trace.parquet` does not come from events. It comes from the kernel ledger patch (the
send and deliver chokepoints), which the `S` and `D` records mirror. Its `seq` is the DELIVER
order of non-wakeup sub-messages and wakeups.

**Logged but NOT consumed.** These were observed with `--events all` on ra01:
`AGENT_TYPE`, `STARTING_CASH`, `HOLDINGS_UPDATED`, `CANCEL_SUBMITTED`, `BID_DEPTH`,
`ASK_DEPTH`, `IMBALANCE`, `LAST_TRADE`, `MARK_TO_MARKET`, `MARKED_TO_MARKET`, `FINAL_HOLDINGS`,
`FINAL_CASH_POSITION`, `ENDING_CASH`, and the exchange's own `QuerySpreadMsg`,
`MarketHoursRequestMsg` and `MarketClosePriceRequestMsg`. The exchange has `log_orders=None`,
so it logs no order messages.
