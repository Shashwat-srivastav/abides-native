# refdump `dump.tsv` format, v1

The file is a step-by-step log of one simulation run. The Python reference writes it with
`refdump.py`. The C++ engine must write the **same bytes** for the same scenario. Then
`first_divergence.py ref.tsv native.tsv` points at the first event where the two engines differ.

## 1. File layout

* UTF-8. Each line ends with `\n` only (no `\r`). Fields are separated by exactly one TAB (`\t`).
* **Comment lines** start with `#`. The comparator ignores them, so they may differ between
  engines. The reference writes these:
  * line 1: `#REFDUMP\tv1\tscenario_id=<id>\tseed=<seed>\tevents=<trace|all>`
  * last lines: `#COUNT\t<type>\t<n>`, one per record type.
* **Record lines** start with a one-letter type, then the type's fixed columns. No column is
  ever empty. A missing or not-applicable value is written as `-`.
* The records appear in the order the events happen in the run (see section 4).

## 2. Value formatting (applies to every column)

| Python value | Written as | Example |
|---|---|---|
| `None` | `-` | `-` |
| `bool` / `np.bool_` | `1` / `0` | `mkt_closed=0` |
| `int`, any numpy integer | decimal, `-` sign if negative, no `+`, no leading zeros | `1612517400000001136` |
| `float`, any numpy float | Python `float.hex()` (C reference below) | `0x1.86a0000000000p+16` |
| `Side` enum | its value | `BID` / `ASK` |
| `str` | as-is; `\` becomes `\\`, TAB becomes `\t`, LF becomes `\n`, CR becomes `\r` (literal backslash sequences); the empty string is `''` | `ABM,100002,10` |
| `tuple` | elements joined by `x` | `(100000, 10)` becomes `100000x10` |
| `list` / 1-D ndarray | `[` + elements joined by `;` + `]` | `[100000x10;99999x5]`, `[]` |
| `dict` | `{` + `key:value` pairs joined by `,` in insertion order + `}` | `{ABM:100000}`, `{}` |
| `Message` object (inside a list) | `<ClassName>#<message_id>` | `LimitOrderMsg#37` |

**Integer and float types matter.** If Python holds a float, the dump shows hex. If it holds
an int, the dump shows decimal. For example, the first megashock time `pt` in the oracle is a
Python float (`mkt_open + exponential(...)`), and later values are ints. A port that uses
the wrong type will diverge in the dump. That is intended, because the type affects the
arithmetic that follows.

### float.hex in C/C++ (tested bit-exact against CPython on 200k random doubles and the edge cases)

```c
// out must hold >= 32 chars
void py_float_hex(double d, char *out) {
    if (isnan(d)) { strcpy(out, "nan"); return; }
    if (isinf(d)) { strcpy(out, d < 0 ? "-inf" : "inf"); return; }
    uint64_t b; memcpy(&b, &d, 8);
    const char *s = (b >> 63) ? "-" : "";
    int e = (int)((b >> 52) & 0x7ff);
    uint64_t m = b & ((1ULL << 52) - 1);
    if (e == 0 && m == 0) { sprintf(out, "%s0x0.0p+0", s); return; }
    int lead = (e == 0) ? 0 : 1;
    int ex   = (e == 0) ? -1022 : e - 1023;
    sprintf(out, "%s0x%d.%013llxp%+d", s, lead, (unsigned long long)m, ex);
}
```
Examples: `1.0` gives `0x1.0000000000000p+0`, `0.0` gives `0x0.0p+0`, `-0.0` gives `-0x0.0p+0`,
`5e-324` gives `0x0.0000000000001p-1022`. The C `%a` format does **not** match this output.

## 3. Record types and columns

Column 0 is the type letter. The columns below are numbered from 1.

### `K`: kernel constructed (exactly one line)
`K  start_time  stop_time  n_agents  default_comp_delay`
* `default_comp_delay` is `agent_computation_delays[0]` right after `Kernel.__init__`. In
  this port it is always 50.

### `W`: `Kernel.set_wakeup` call
`W  t  agent  wake_at  message_id`
* `t` is the kernel `current_time` at the call.
* `wake_at` is the requested time. When the request is `None`, it is `current_time+1`.
* `message_id` is the id of the `WakeupMsg` that was created.

### `D`: kernel dispatch (one line per heap pop in `Kernel.runner`)
`D  t  kind  disp  sender  recipient  msg_class  message_id  requeue_to  batch_id  order_id  side  limit_price  quantity  fill_price  payload`
* `t` is the delivery time popped from the heap. It becomes the kernel's `current_time`.
* `kind` is `WAKEUP` for a `WakeupMsg`, otherwise `MSG`.
* `disp`:
  * `REQUEUE` means `agent_current_times[recipient] > t`. The kernel pushes the item back with
    priority `requeue_to`, which is that agent time. The agent does not run, and the item
    appears again later as another `D`.
  * `DELIVER` means `wakeup()` or `receive_message()` is called. `requeue_to` is `-`.
* `batch_id` is `-` except when a delivered `MessageBatch` is split. In that case there is
  one `D` line per sub-message, and each carries its own class and id plus the batch's id.
  A requeued batch is one line with class `MessageBatch`. The fork agents never send batches.
* Order columns: `order_id side limit_price quantity fill_price` are taken from `msg.order`,
  or from `msg.new_order` when the message has no `.order`. They are all `-` if the message
  has neither. A `MarketOrder` has `limit_price` `-`. The values are read **at pop time**,
  before the handler runs (Python messages hold references to live order objects).
* `payload` (see 3.1) holds the message's other dataclass fields.

### `S`: `Kernel.send_message` call (written after the call returns)
`S  t  sender  recipient  msg_class  message_id  comp_delay  add_delay  delay  sent_time  latency_raw  latency  deliver_at  order_id  side  limit_price  quantity  fill_price  payload`
* `comp_delay` is `agent_computation_delays[sender]` at call time. The exchange sets its own
  to `computation_delay` on every message it receives (0 in every public scenario) and to 0
  for MarketHours.
* `add_delay` is `current_agent_additional_delay`.
* `delay` is the per-message `delay` argument (the exchange passes `pipeline_delay` for
  OrderAccepted, OrderCancelled and OrderExecuted).
* `sent_time = t + comp_delay + add_delay + delay`.
* `latency_raw` is the value `agent_latency_model.get_latency()` returned, formatted with
  its own type (an int for `ScenarioLatencyModel`). It is `-` when no model was called.
* `latency = deliver_at - sent_time`, the realized integer latency.
* `deliver_at` is the heap priority the message was queued with.
* The order and payload columns are the same as in `D`, but read at **send** time.
* A message sent to several recipients (for example `MarketClosePriceMsg`) gives one `S` per
  recipient, all with the same `message_id`.

### `R`: RandomState draw (every outermost call on any stream; written after the draw)
`R  t  owner  method  args  result`
* `t` is the kernel `current_time`, or `-` before the Kernel exists (for draws inside
  `build_config`).
* `owner`:
  * `global`: numpy's module-level `np.random.*` stream. It covers `seed`, the seed-drawing
    `randint`, and the oracle megashock `exponential`.
  * `oracle`: `symbols['ABM']['random_state']`, used for OU normals and megashock normal/randint.
  * `<agent id>` in decimal: that agent's `random_state`. `0` is the exchange.
  * `latency`: the `ScenarioLatencyModel` stream.
  * `kernel`: the `Kernel.random_state`. `abides.run` builds it as `RandomState(seed=0)`. It is
    only used when there is no latency model, so it never draws here.
  * `cfgkernel`: `config['random_state_kernel']`. It is drawn from the global stream (that
    draw is logged) but never passed to the Kernel, so it never draws.
* `method` is the numpy method name: `seed randint normal uniform lognormal pareto exponential
  choice rand random_sample ...`.
* `args` are canonical positional parameters in numpy signature order, all filled in (defaults
  included), joined by `,`:

  | method | args |
  |---|---|
  | `normal` | `loc(f),scale(f),size` |
  | `uniform` | `low(f),high(f),size` |
  | `lognormal` | `mean(f),sigma(f),size` |
  | `pareto` | `a(f),size` |
  | `exponential` | `scale(f),size` |
  | `randint` | `low(i),high(i or -),size,dtype` where dtype is a numpy dtype name (`int64` for the default `int`, `uint64` for the seed draws) |
  | `choice` | `a,size,replace(1/0),p` |
  | `seed` | `seed` |
  | `rand`, `randn` | the dimension ints, or `-` |

  `(f)` parameters are always converted to float and written as hex, even when Python passed
  an int. For example, `observe_price` passes an int `loc=r_t`, which is written as a hex float.
  `(i)` parameters are decimal. `size` is `-` for None, the int itself, or dims joined by `x`.
* `result` is the scalar formatted by section 2. An array result is `[..;..]`. `seed` gives `-`.
* Nested draws (numpy methods that call other methods internally, such as `choice` calling
  `randint`) are not logged. Only the outermost call is.

### `E`: agent log event (`Agent.logEvent`, written before the event is appended)
`E  t  agent  event_type  order_id  side  limit_price  quantity  fill_price  payload`
* `t` is the logging agent's `current_time` (the `EventTime` that trace.py sorts on).
* When the event is an order dict (`order.to_dict()`), the five order columns are filled and
  `payload` is `-`. Otherwise the order columns are `-` and `payload` is the formatted event.
  `BEST_BID` and `BEST_ASK` give the string `ABM,<price>,<total_qty>`.
* By default (`--events trace`) only the event types that trace.py consumes are written:
  `ORDER_SUBMITTED ORDER_ACCEPTED ORDER_EXECUTED ORDER_CANCELLED ORDER_REPLACED BEST_BID BEST_ASK`.
  `--events all` writes every event, including `AGENT_TYPE`, `HOLDINGS_UPDATED`, `LAST_TRADE`,
  `STARTING_CASH`, `MARKED_TO_MARKET`, `QuerySpreadMsg` and others, and uses ad-hoc formatting
  for non-order dicts. Compare those dumps only against the reference, not against a C++ dump.

### `F`: oracle fundamental step (`SparseMeanRevertingOracle.compute_fundamental_at_timestamp`)
`F  t  ts  v_adj  pt  pv  v`
* One line per OU advance: to each megashock time, then to the requested time.
* `v_adj` is `0` (int) for the final step and the megashock value (a hex float) for a
  megashock step.
* `pt` can be a hex float. The first megashock time is float-valued, see section 2.
* `v` is the new integer fundamental after rounding, the floor at 0, and any scheduled jump.
* A call that returns early (`current_time <= pt`) writes nothing.

### 3.1 `payload` column

The payload is the message's dataclass fields in declaration order (base classes first),
written as `name=value` pairs joined by `;`. `message_id`, `order` and `new_order` are left out
because they already have their own columns. `old_order` is written as `old=<order_id>`. A
message with no remaining fields has payload `-`. Payloads for the classes that occur:

| msg_class | payload |
|---|---|
| `WakeupMsg`, `MarketHoursRequestMsg`, `MarketClosePriceRequestMsg`, `MarketClosedMsg`, `LimitOrderMsg`, `MarketOrderMsg`, `OrderAcceptedMsg`, `OrderExecutedMsg`, `OrderCancelledMsg`, `OrderModifiedMsg`, `OrderPartialCancelledMsg` | `-` |
| `MarketHoursMsg` | `mkt_open=<ns>;mkt_close=<ns>` |
| `MarketClosePriceMsg` | `close_prices={ABM:<price or ->}` |
| `QuerySpreadMsg` | `symbol=ABM;depth=<n>` |
| `QuerySpreadResponseMsg` | `symbol=ABM;mkt_closed=<0/1>;depth=<n>;bids=[pxq;...];asks=[pxq;...];last_trade=<price or ->` |
| `QueryLastTradeMsg` / `...ResponseMsg` | `symbol=ABM` / `symbol=ABM;mkt_closed=<0/1>;last_trade=<p or ->` |
| `CancelOrderMsg` | `tag=<tag or ->;metadata={}` |
| `PartialCancelOrderMsg` | `quantity=<n>;tag=..;metadata={..}` |
| `ModifyOrderMsg` / `OrderReplacedMsg` | `old=<old order_id>` |
| `ReplaceOrderMsg` | `agent_id=<id>;old=<old order_id>` |
| `MessageBatch` | `messages=[<Class>#<id>;...]` |

## 4. Ordering rules (what "same order" means)

* The global and oracle `R` records from `build_config` come first, then `K`, then the `W`
  records from `kernel_starting` (agent 0 first, then agents in id order), then the main loop.
* A record is written when its action finishes. A `D` line is written at the heap pop, before
  the handler runs. Everything the handler causes follows it, in call order: `R` draws, `S`
  sends (each `S` comes after the `R` latency draw it caused), `W`, `E`, and `F`.
* Heap order is by `(time, sender_id, recipient_id, message_id)`, because the heap compares
  the tuple `(t, (sender, recipient, msg))`, and `Message.__lt__` compares `message_id`. A C++
  engine must break ties the same way to produce identical `D` order.
* Main-loop termination: the loop checks `current_time <= stop_time` **before** each pop. So
  the first item past `stop_time` is still popped and dispatched, and appears as a `D`.

## 5. What a C++ port must emit

Emit `K W D S R E F` exactly as above. If a record type is not implemented yet, compare with
`first_divergence.py --types D,S` (or another subset). The filter is applied to both files
before records are paired.
