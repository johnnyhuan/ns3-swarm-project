#!/usr/bin/env python3
"""
Independent P2 cross-check. Reads the verify_*.csv logs written by
`scratch/lr-wpan-swarm --verifyLog=true` and re-checks every counted reception from first
principles, without using any of the simulator's own decisions:

  for every P2 packet the receiver counted as received:
    V1  the sender really transmitted in that cycle, in that slot
    V2  that transmission was not cut off at the slot end
    V3  the receiver's radio was on the sender's channel in that slot
    V4  the receiver was not transmitting itself at that time
    V5  SINR >= lock threshold during the whole packet, recomputed here from the logged
        positions, the path-loss formula and every overlapping co-channel transmission
  for every evaluated Top-5 link:
    V6  'delivered' in the evaluation  => a valid reception exists
    V7  a valid reception exists       => 'delivered' in the evaluation

Also reports (not errors): borderline receptions, losses where an earlier-starting packet on the
same channel locked first (no re-sync), and 'unexplained losses' (not delivered although the
receiver was tuned, idle, SINR >= lock + 1 dB and nothing locked earlier).

Usage:
    python3 verify_crosscheck.py <run_dir> --p2power 4
    python3 verify_crosscheck.py <run_dir> --p2power 4 --timeline <node> <epoch>
"""
import argparse
import csv
import math
import os
from collections import defaultdict

PL_REF, PL_EXP = 46.6777, 3.0           # log-distance path loss at 1 m, exponent
BROADCAST_CHANNEL = 11                  # P1 channel; the radio is still there when P2 starts


def rx_dbm(p_tx, a, b):
    d = max(0.1, math.dist(a, b))
    return p_tx - PL_REF - 10 * PL_EXP * math.log10(d)


def mw(dbm):
    return 10 ** (dbm / 10.0)


def load(run_dir):
    def rows(name):
        with open(os.path.join(run_dir, name), newline="") as f:
            return list(csv.DictReader(f))

    pos = {(int(r["epoch"]), int(r["node"])): (float(r["x"]), float(r["y"]), float(r["z"]))
           for r in rows("verify_pos.csv")}
    tx = [dict(epoch=int(r["epoch"]), sender=int(r["sender"]), slot=int(r["slot"]), ch=int(r["channel"]),
               start=float(r["start_us"]), end=float(r["end_us"]), cut=int(r["cut"])) for r in rows("verify_tx.csv")]
    sched = defaultdict(dict)
    for r in rows("verify_sched.csv"):
        sched[(int(r["epoch"]), int(r["node"]))][int(r["slot"])] = (r["action"], int(r["channel"]), int(r["target"]))
    rx = [dict(epoch=int(r["epoch"]), rx=int(r["rx"]), tx=int(r["tx"]), t=float(r["time_us"]), slot=int(r["slot"]),
               valid=int(r["valid"])) for r in rows("verify_rx.csv")]
    links = [dict(epoch=int(r["epoch"]), rx=int(r["rx"]), tx=int(r["tx"]), dist=float(r["dist"]),
                  delivered=int(r["delivered"])) for r in rows("verify_links.csv")]
    return pos, tx, sched, rx, links


class Model:
    def __init__(self, run_dir, p2power, sens=-94.0, lock=6.0, idle_rx=False):
        self.idle_rx = idle_rx   # False (default): the radio is off in P2 slots with nothing scheduled
        self.pos, self.tx, self.sched, self.rx, self.links = load(run_dir)
        self.p, self.lock, self.sens = p2power, lock, sens
        self.noise_mw = mw(sens - lock)
        self.by_ch = defaultdict(list)          # (epoch, channel) -> tx rows
        self.by_sender = defaultdict(list)      # (epoch, sender) -> tx rows
        for t in self.tx:
            self.by_ch[(t["epoch"], t["ch"])].append(t)
            self.by_sender[(t["epoch"], t["sender"])].append(t)

    def radio_channel(self, epoch, node, slot):
        """Channel the node's radio is on in `slot` (None = radio off). With idle listening an IDLE
        slot keeps the last channel used; without it the radio is off in IDLE slots."""
        sch = self.sched.get((epoch, node), {})
        if not self.idle_rx:
            return sch[slot][1] if slot in sch else None
        for s in range(slot, -1, -1):
            if s in sch:
                return sch[s][1]
        return BROADCAST_CHANNEL

    def transmitting(self, epoch, node, start, end):
        return any(t["start"] < end and t["end"] > start for t in self.by_sender[(epoch, node)])

    def min_sinr(self, t, rx_node):
        """Lowest SINR (dB) of packet t at rx_node over its air time, piecewise over overlaps."""
        e = t["epoch"]
        if (e, t["sender"]) not in self.pos or (e, rx_node) not in self.pos:
            return None, None
        rpos = self.pos[(e, rx_node)]
        sig = rx_dbm(self.p, self.pos[(e, t["sender"])], rpos)
        intf = [o for o in self.by_ch[(e, t["ch"])]
                if o is not t and o["sender"] not in (t["sender"], rx_node)
                and o["start"] < t["end"] and o["end"] > t["start"] and (e, o["sender"]) in self.pos]
        cuts = sorted({t["start"], t["end"]} | {max(t["start"], o["start"]) for o in intf}
                      | {min(t["end"], o["end"]) for o in intf})
        worst = None
        for a, b in zip(cuts, cuts[1:]):
            if b - a <= 1e-6:
                continue
            i_mw = sum(mw(rx_dbm(self.p, self.pos[(e, o["sender"])], rpos)) for o in intf if o["start"] < b and o["end"] > a)
            sinr = sig - 10 * math.log10(i_mw + self.noise_mw)
            worst = sinr if worst is None else min(worst, sinr)
        return worst, sig

    def check(self, tol=0.5):
        v = defaultdict(list)
        border = 0
        valid = [r for r in self.rx if r["valid"]]
        for r in valid:
            cand = [t for t in self.by_sender[(r["epoch"], r["tx"])] if t["slot"] == r["slot"]]
            if not cand:
                v["V1 no matching TX"].append(r)
                continue
            t = cand[0]
            if t["cut"]:
                v["V2 TX was cut off"].append(r)
            if self.radio_channel(r["epoch"], r["rx"], r["slot"]) != t["ch"]:
                v["V3 receiver on another channel"].append(r)
            if self.transmitting(r["epoch"], r["rx"], t["start"], t["end"]):
                v["V4 receiver was transmitting"].append(r)
            s, _ = self.min_sinr(t, r["rx"])
            if s is None:
                continue
            if s < self.lock - tol:
                v["V5 SINR below lock"].append(dict(r, sinr=round(s, 2)))
            elif s < self.lock + tol:
                border += 1
        got = {(r["epoch"], r["rx"], r["tx"]) for r in valid}
        for l in self.links:
            k = (l["epoch"], l["rx"], l["tx"])
            if l["delivered"] and k not in got:
                v["V6 delivered without reception"].append(l)
            if not l["delivered"] and k in got:
                v["V7 reception not counted"].append(l)
        # Unexplained losses (information only)
        unexplained, locked_first = [], []
        for l in self.links:
            if l["delivered"]:
                continue
            for t in self.by_sender[(l["epoch"], l["tx"])]:
                if t["cut"] or self.radio_channel(l["epoch"], l["rx"], t["slot"]) != t["ch"]:
                    continue
                if self.transmitting(l["epoch"], l["rx"], t["start"], t["end"]):
                    continue
                s, _ = self.min_sinr(t, l["rx"])
                if s is not None and s >= self.lock + 1.0:
                    # Explained: another packet on this channel started earlier and was strong enough
                    # to lock on its own (>= sensitivity); BLE receivers never re-sync, so the wanted
                    # packet that arrives during it is dropped.
                    e, rpos = l["epoch"], self.pos.get((l["epoch"], l["rx"]))
                    early = [o for o in self.by_ch[(e, t["ch"])]
                             if o["sender"] not in (t["sender"], l["rx"]) and o["start"] < t["start"] < o["end"]
                             and (e, o["sender"]) in self.pos and rpos is not None
                             and rx_dbm(self.p, self.pos[(e, o["sender"])], rpos) >= self.sens]
                    if early:
                        locked_first.append(dict(l, slot=t["slot"], sinr=round(s, 2)))
                    else:
                        unexplained.append(dict(l, slot=t["slot"], sinr=round(s, 2)))
                    break
        return dict(valid_rx=len(valid), bad_rx=len(self.rx) - len(valid), links=len(self.links),
                    delivered=sum(l["delivered"] for l in self.links), violations=v, borderline=border,
                    unexplained=unexplained, locked_first=locked_first)

    def timeline(self, node, epoch):
        out = [f"Timeline of UAV {node} in cycle {epoch}  (P2 TX power {self.p} dBm, noise {10 * math.log10(self.noise_mw):.0f} dBm, lock {self.lock} dB)"]
        if (epoch, node) not in self.pos:
            return out[0] + "\n  (no data)\n"
        me = self.pos[(epoch, node)]
        out.append(f"position {me}")
        tops = [l for l in self.links if l["epoch"] == epoch and l["rx"] == node]
        out.append("Ground-truth Top-5 (<= 50 m): " + ", ".join(f"UAV {l['tx']} {l['dist']:.1f} m {'OK' if l['delivered'] else 'LOST'}" for l in tops))
        got = {(r["tx"], r["slot"]) for r in self.rx if r["epoch"] == epoch and r["rx"] == node and r["valid"]}
        sch = self.sched.get((epoch, node), {})
        out.append(f"{'slot':>4}  {'my action':<22} {'packets on my channel in this slot (sender: distance, RX power, SINR -> result)'}")
        nslots = 1 + max([t["slot"] for t in self.tx if t["epoch"] == epoch] + list(sch.keys()) + [0])
        for s in range(nslots):
            ch = self.radio_channel(epoch, node, s)
            a = sch.get(s)
            act = "IDLE (stay ch %d)" % ch if a is None else (f"TX ch {a[1]}" if a[0] == "TX" else f"RX ch {a[1]} -> UAV {a[2]}")
            pk = []
            for t in self.by_ch[(epoch, ch)]:
                if t["slot"] != s or t["sender"] == node or (epoch, t["sender"]) not in self.pos:
                    continue
                d = math.dist(me, self.pos[(epoch, t["sender"])])
                sinr, sig = self.min_sinr(t, node)
                res = "RECEIVED" if (t["sender"], s) in got else "-"
                pk.append(f"{t['sender']}: {d:.1f} m, {sig:.1f} dBm, SINR {sinr:.1f} dB -> {res}")
            if a is None and not pk:
                continue
            out.append(f"{s:>4}  {act:<22} " + ("; ".join(pk) if pk else "(nothing heard)"))
        return "\n".join(out) + "\n"


def report(res):
    lines = [f"valid receptions {res['valid_rx']}, rejected by payload check {res['bad_rx']}, "
             f"Top-5 links {res['links']} (delivered {res['delivered']})"]
    names = ["V1 no matching TX", "V2 TX was cut off", "V3 receiver on another channel", "V4 receiver was transmitting",
             "V5 SINR below lock", "V6 delivered without reception", "V7 reception not counted"]
    for n in names:
        lines.append(f"  {n:34s}: {len(res['violations'][n])}")
        for ex in res["violations"][n][:3]:
            lines.append(f"      e.g. {ex}")
    lines.append(f"  borderline receptions (lock +-0.5 dB) : {res['borderline']}")
    lines.append(f"  lost because an earlier packet locked first (no re-sync, sender skipped the channel switch): {len(res['locked_first'])}")
    lines.append(f"  unexplained losses (tuned, idle, SINR >= lock+1 dB, nothing earlier): {len(res['unexplained'])}")
    for ex in res["unexplained"][:3]:
        lines.append(f"      e.g. {ex}")
    return "\n".join(lines)


# ----------------------------------------------------------------------------------------------
# P1 (discovery beacons, all on the broadcast channel)
# ----------------------------------------------------------------------------------------------
class P1Model:
    """Same idea for P1: every counted beacon reception is re-checked from the logs."""
    TURNAROUND_US = 40.0

    def __init__(self, run_dir, p1power, sens=-94.0, lock=6.0):
        def rows(name):
            with open(os.path.join(run_dir, name), newline="") as f:
                return list(csv.DictReader(f))
        self.p, self.lock, self.sens = p1power, lock, sens
        self.noise_mw = mw(sens - lock)
        self.pos = {(int(r["epoch"]), int(r["node"])): (float(r["x"]), float(r["y"]), float(r["z"]))
                    for r in rows("verify_p1_pos.csv")}
        self.tx = [dict(epoch=int(r["epoch"]), sender=int(r["sender"]), uid=int(r["uid"]), slot=int(r["slot"]),
                        start=float(r["start_us"]), end=float(r["end_us"]), cut=int(r["cut"])) for r in rows("verify_p1_tx.csv")]
        self.rx = [dict(epoch=int(r["epoch"]), rx=int(r["rx"]), tx=int(r["tx"]), uid=int(r["uid"]), t=float(r["time_us"]))
                   for r in rows("verify_p1_rx.csv")]
        self.links = [dict(epoch=int(r["epoch"]), rx=int(r["rx"]), tx=int(r["tx"]), dist=float(r["dist"]),
                           delivered=int(r["delivered"])) for r in rows("verify_p1_links.csv")]
        self.by_uid = {t["uid"]: t for t in self.tx}
        self.by_epoch = defaultdict(list)
        self.by_sender = defaultdict(list)
        for t in self.tx:
            self.by_epoch[t["epoch"]].append(t)
            self.by_sender[(t["epoch"], t["sender"])].append(t)

    def busy_own_tx(self, epoch, node, start, end, guard=0.0):
        """Node transmitting (or turning its radio around, with guard) during [start, end]."""
        return any(t["start"] - guard < end and t["end"] + guard > start for t in self.by_sender[(epoch, node)])

    def min_sinr(self, t, rx_node):
        e = t["epoch"]
        if (e, t["sender"]) not in self.pos or (e, rx_node) not in self.pos:
            return None, None
        rpos = self.pos[(e, rx_node)]
        sig = rx_dbm(self.p, self.pos[(e, t["sender"])], rpos)
        intf = [o for o in self.by_epoch[e] if o is not t and o["sender"] not in (t["sender"], rx_node)
                and o["start"] < t["end"] and o["end"] > t["start"] and (e, o["sender"]) in self.pos]
        cuts = sorted({t["start"], t["end"]} | {max(t["start"], o["start"]) for o in intf} | {min(t["end"], o["end"]) for o in intf})
        worst = None
        for a, b in zip(cuts, cuts[1:]):
            if b - a <= 1e-6:
                continue
            i_mw = sum(mw(rx_dbm(self.p, self.pos[(e, o["sender"])], rpos)) for o in intf if o["start"] < b and o["end"] > a)
            sinr = sig - 10 * math.log10(i_mw + self.noise_mw)
            worst = sinr if worst is None else min(worst, sinr)
        return worst, sig

    def check(self, tol=0.5):
        v = defaultdict(list)
        border = 0
        for r in self.rx:
            t = self.by_uid.get(r["uid"])
            if t is None or t["sender"] != r["tx"] or t["epoch"] != r["epoch"]:
                v["V1 no matching TX (wrong sender/cycle)"].append(r)
                continue
            if t["cut"]:
                v["V2 TX was cut off"].append(r)
            if self.busy_own_tx(r["epoch"], r["rx"], t["start"], t["end"]):
                v["V4 receiver was transmitting"].append(r)
            s, _ = self.min_sinr(t, r["rx"])
            if s is None:
                continue
            if s < self.lock - tol:
                v["V5 SINR below lock"].append(dict(r, sinr=round(s, 2)))
            elif s < self.lock + tol:
                border += 1
        got = {(r["epoch"], r["rx"], r["tx"]) for r in self.rx}
        for l in self.links:
            k = (l["epoch"], l["rx"], l["tx"])
            if l["delivered"] and k not in got:
                v["V6 delivered without reception"].append(l)
            if not l["delivered"] and k in got:
                v["V7 reception not counted"].append(l)
        locked_first, turnaround, unexplained = [], [], []
        for l in self.links:
            if l["delivered"]:
                continue
            e = l["epoch"]
            for t in self.by_sender[(e, l["tx"])]:
                if t["cut"] or self.busy_own_tx(e, l["rx"], t["start"], t["end"]):
                    continue
                s, _ = self.min_sinr(t, l["rx"])
                if s is None or s < self.lock + 1.0:
                    continue
                rpos = self.pos.get((e, l["rx"]))
                early = [o for o in self.by_epoch[e] if o["sender"] not in (t["sender"], l["rx"]) and o["start"] < t["start"] < o["end"]
                         and (e, o["sender"]) in self.pos and rx_dbm(self.p, self.pos[(e, o["sender"])], rpos) >= self.sens]
                if early:
                    locked_first.append(dict(l, sinr=round(s, 2)))
                elif self.busy_own_tx(e, l["rx"], t["start"], t["end"], guard=self.TURNAROUND_US):
                    turnaround.append(dict(l, sinr=round(s, 2)))
                else:
                    unexplained.append(dict(l, sinr=round(s, 2), start=t["start"]))
                break
        return dict(valid_rx=len(self.rx), links=len(self.links), delivered=sum(l["delivered"] for l in self.links),
                    violations=v, borderline=border, locked_first=locked_first, turnaround=turnaround, unexplained=unexplained)


P1_NAMES = ["V1 no matching TX (wrong sender/cycle)", "V2 TX was cut off", "V4 receiver was transmitting",
            "V5 SINR below lock", "V6 delivered without reception", "V7 reception not counted"]


def report_p1(res):
    lines = [f"beacon receptions {res['valid_rx']}, Top-5 links {res['links']} (delivered {res['delivered']})"]
    for n in P1_NAMES:
        lines.append(f"  {n:38s}: {len(res['violations'][n])}")
        for ex in res["violations"][n][:3]:
            lines.append(f"      e.g. {ex}")
    lines.append(f"  borderline receptions (lock +-0.5 dB)     : {res['borderline']}")
    lines.append(f"  lost: an earlier beacon locked first (no re-sync)      : {len(res['locked_first'])}")
    lines.append(f"  lost: receiver in RX/TX turnaround (own beacon <=40 us) : {len(res['turnaround'])}")
    lines.append(f"  unexplained losses                                     : {len(res['unexplained'])}")
    for ex in res["unexplained"][:3]:
        lines.append(f"      e.g. {ex}")
    return "\n".join(lines)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("run_dir")
    ap.add_argument("--p2power", type=float, default=4.0)
    ap.add_argument("--p1", type=float, metavar="P1POWER", help="check P1 beacons instead (P1 TX power in dBm)")
    ap.add_argument("--timeline", type=int, nargs=2, metavar=("NODE", "EPOCH"))
    a = ap.parse_args()
    if a.p1 is not None:
        print(report_p1(P1Model(a.run_dir, a.p1).check()))
        raise SystemExit
    m = Model(a.run_dir, a.p2power)
    if a.timeline:
        print(m.timeline(*a.timeline))
    else:
        print(report(m.check()))
