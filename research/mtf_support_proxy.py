"""Causal 4h double-pivot support proxy; NOT Pine Strong MTF SR v3.3 parity.

Recognition of each zone is delayed until two distinct pivots both have a
3-bar reaction confirmed. Never expose a zone earlier than that observation.
Zone invalidation after two completed 4h closes below the lower edge.
"""
from __future__ import annotations


def wilder_atr(bars, period=14):
    out=[]
    value=None
    initial=[]
    for i,b in enumerate(bars):
        high,low=b["high"],b["low"]
        prev=bars[i-1]["close"] if i else b["close"]
        tr=max(high-low,abs(high-prev),abs(low-prev))
        if value is None:
            initial.append(tr)
            if len(initial)==period:
                value=sum(initial)/period
        else:
            value=(value*(period-1)+tr)/period
        out.append(value)
    return out


def aggregate_4h(hourly):
    result=[]
    for i in range(0,len(hourly)-3,4):
        chunk=hourly[i:i+4]
        if len(chunk)<4 or any(chunk[k][0]-chunk[k-1][0]!=3600000 for k in (1,2,3)):
            raise ValueError("Missing hourly bar in 4h aggregation")
        if chunk[0][0]%(4*3600000)!=0:
            raise ValueError("Hourly series must begin at a UTC 4h boundary")
        result.append({"last_hour_index":i+3,
                       "open":chunk[0][1],"high":max(x[2] for x in chunk),
                       "low":min(x[3] for x in chunk),"close":chunk[-1][4]})
    return result


def confirmed_support_zones(hourly, *, left=3, right=1, reaction=3,
                            min_gap=4, reaction_atr=0.8, radius_atr=0.30,
                            min_radius_fraction=0.0005, expiry_4h=360):
    """Return (available_hour, expire_hour, center, half_width) tuples.

    Heuristic proxy for independent tests, NOT the supplied 28k-char Pine
    script's clustering, latching, scoring, multi-TF zones or validity rules.
    """
    source=aggregate_4h(hourly)
    a=wilder_atr(source)
    clusters=[]
    zones=[]
    for observed in range(max(left+right+reaction, 20),len(source)):
        p=observed-reaction
        if p<left or observed<p+right or a[p] is None:
            continue
        pivot=source[p]["low"]
        if not (pivot<min(source[k]["low"] for k in range(p-left,p)) and
                pivot<=min(source[k]["low"] for k in range(p+1,p+right+1))):
            continue
        if max(source[k]["close"] for k in range(p+1,observed+1))-pivot<reaction_atr*a[p]:
            continue
        if min(source[k]["close"] for k in range(p+1,observed+1))<pivot-0.30*a[p]:
            continue
        width=max(radius_atr*a[p],min_radius_fraction*pivot)
        matched=None
        for z in clusters:
            if abs(z["center"]-pivot)>max(z["width"],width) or p-z["last_pivot"]<min_gap:
                continue
            between=source[z["last_pivot"]+1:p]
            if not between or max(x["high"] for x in between)<z["center"]+reaction_atr*a[p]:
                continue
            matched=z
            break
        if matched is None:
            clusters.append({"center":pivot,"width":width,"tests":1,"last_pivot":p})
        else:
            matched["center"]=(matched["center"]*matched["tests"]+pivot)/(matched["tests"]+1)
            matched["width"]=max(matched["width"],width)
            matched["tests"]+=1
            matched["last_pivot"]=p
            if matched["tests"]==2:
                avail=source[observed]["last_hour_index"]
                lower=matched["center"]-matched["width"]
                expired=min(len(source), observed+expiry_4h+1)
                for k in range(observed+2,expired):
                    if source[k]["close"]<lower and source[k-1]["close"]<lower:
                        expired=k
                        break
                expire_hour=min(len(hourly),source[expired]["last_hour_index"]+1) if expired<len(source) else len(hourly)
                zones.append((avail,expire_hour,matched["center"],matched["width"]))
    return zones


def near_confirmed_support(zones, index, price, atr_1h, *, extra_atr=0.5):
    if atr_1h is None:
        return False
    return any(available<=index<expires and abs(price-center)<=width+extra_atr*atr_1h
               for available,expires,center,width in zones)
