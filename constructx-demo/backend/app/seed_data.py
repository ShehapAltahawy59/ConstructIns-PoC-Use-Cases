"""Generate realistic seed data for the Procore-style SOV model.

Projects, companies, subcontracts, Schedule-of-Values line items, and monthly
progress claims. Deterministic via a fixed seed.
"""
from __future__ import annotations

import datetime as dt
import random

PROJECTS = [
    ("P1", "Tower A", "Nasr Development", "Active"),
    ("P2", "Bridge", "Ministry of Roads", "Active"),
    ("P3", "Mall", "Cairo Retail Group", "Active"),
    ("P4", "Hospital", "Health Authority", "Active"),
    ("P5", "Airport", "Civil Aviation", "Active"),
    ("P6", "Office Park", "Delta Estates", "Active"),
    ("P7", "Residential Compound", "Green Homes", "Active"),
    ("P8", "Factory", "Industrial Co", "Active"),
    ("P9", "University", "Education Trust", "Planned"),
]

COMPANIES = [
    ("V001", "ABC Electrical", "Electrical"), ("V002", "XYZ Concrete", "Concrete"),
    ("V003", "Delta HVAC", "HVAC"), ("V004", "Future Plumbing", "Plumbing"),
    ("V005", "IronCore Steel", "Steel"), ("V006", "PrimePaint", "Painting"),
    ("V007", "FineFinish", "Finishing"), ("V008", "SafeGuard Fire", "Fire Fighting"),
    ("V009", "FloorMasters", "Flooring"), ("V010", "SolidMasonry", "Masonry"),
    ("V011", "MechPro", "Mechanical"), ("V012", "Volt Electric", "Electrical"),
    ("V013", "RockSolid Concrete", "Concrete"), ("V014", "CoolAir HVAC", "HVAC"),
    ("V015", "AquaFlow Plumbing", "Plumbing"), ("V016", "SteelLine", "Steel"),
    ("V017", "ColorWorks", "Painting"), ("V018", "Elite Finishing", "Finishing"),
    ("V019", "GuardTech Fire", "Fire Fighting"), ("V020", "PrimeFloor", "Flooring"),
    ("V021", "BuildRight Masonry", "Masonry"), ("V022", "PowerMech", "Mechanical"),
]

# Cost codes typical for each trade (CSI-style), plus shared items.
TRADE_CODES = {
    "Electrical": [("16-10", "Wiring & conduit"), ("16-50", "Lighting"), ("16-70", "Low voltage")],
    "Concrete": [("03-30", "Cast-in-place concrete"), ("03-20", "Reinforcement"), ("03-10", "Formwork")],
    "HVAC": [("15-70", "Air handling"), ("15-80", "Ductwork"), ("15-90", "Controls")],
    "Plumbing": [("15-40", "Piping"), ("15-45", "Fixtures"), ("15-30", "Drainage")],
    "Steel": [("05-10", "Structural steel"), ("05-50", "Metal fabrications"), ("05-30", "Decking")],
    "Painting": [("09-90", "Painting"), ("09-91", "Coatings")],
    "Finishing": [("09-25", "Plaster"), ("09-51", "Ceilings"), ("09-70", "Wall finishes")],
    "Fire Fighting": [("15-30", "Sprinklers"), ("13-90", "Fire pumps")],
    "Flooring": [("09-65", "Resilient flooring"), ("09-68", "Carpet"), ("09-30", "Tiling")],
    "Masonry": [("04-20", "Unit masonry"), ("04-40", "Stone")],
    "Mechanical": [("15-10", "Mechanical piping"), ("15-20", "Pumps"), ("15-60", "Equipment")],
}
ACTIVE_PROJECTS = ["P1", "P2", "P3", "P4", "P5", "P6", "P7", "P8"]


def generate(seed: int = 7):
    rng = random.Random(seed)
    today = dt.date.today()
    proj_names = {p[0]: p[1] for p in PROJECTS}

    projects = [dict(project_id=pid, name=name, client=client,
                     start_date=today - dt.timedelta(days=rng.randint(150, 400)),
                     planned_end_date=today + dt.timedelta(days=rng.randint(120, 500)),
                     status=status)
                for pid, name, client, status in PROJECTS]

    companies = [dict(vendor_id=vid, company_name=cn, trade=tr,
                      capacity_projects=rng.randint(2, 5))
                 for vid, cn, tr in COMPANIES]

    latent = {vid: rng.uniform(0.45, 0.98) for vid, _, _ in COMPANIES}

    subcontracts, sov_lines, claims = [], [], []
    sid = 1
    for vid, cn, trade in COMPANIES:
        q = latent[vid]
        nproj = rng.choices([1, 2, 3], weights=[45, 40, 15])[0]
        for pid in rng.sample(ACTIVE_PROJECTS, nproj):
            scode = f"S{sid:03d}"
            start = today - dt.timedelta(days=rng.randint(60, 220))
            dur = rng.randint(180, 420)
            planned_end = start + dt.timedelta(days=dur)
            planned_now = max(0.0, min(1.0, (today - start).days / dur)) * 100

            # target actual: reliable companies track close to plan.
            target_actual = max(2.0, min(100.0,
                                planned_now * (0.6 + 0.4 * q) + rng.uniform(-6, 6)))

            contract = round(rng.uniform(250_000, 950_000))
            codes = list(TRADE_CODES.get(trade, [("01-00", "General")]))
            nlines = min(len(codes), rng.randint(2, 3)) + 1
            # split contract into nlines
            weights = [rng.uniform(0.5, 1.5) for _ in range(nlines)]
            wsum = sum(weights)
            for i in range(nlines):
                cc, desc = (codes[i] if i < len(codes)
                            else ("01-50", "General conditions"))
                sval = round(contract * weights[i] / wsum)
                # each line's % varies around the target actual
                pct = max(0.0, min(100.0, target_actual + rng.uniform(-12, 12)))
                sov_lines.append(dict(
                    line_id=f"{scode}-L{i+1}", subcontract_id=scode,
                    cost_code=cc, description=desc,
                    scheduled_value=sval, percent_complete=round(pct, 1)))

            delay = max(0, round((1 - q) * 20 + rng.uniform(-3, 3)))
            subcontracts.append(dict(
                subcontract_id=scode, vendor_id=vid, project_id=pid,
                title=f"{trade} — {proj_names[pid]}",
                start_date=start, planned_end_date=planned_end, status="Active",
                retainage_pct=rng.choice([5, 10]),
                quality_score=round(max(35, min(100, 55 + 40 * q + rng.uniform(-8, 8))), 1),
                safety_score=round(max(40, min(100, 60 + 37 * q + rng.uniform(-7, 7))), 1),
                inspection_pass=round(max(50, min(100, 70 + 28 * q + rng.uniform(-6, 6))), 1),
                delay_days=int(delay),
                open_issues=int(max(0, round((1 - q) * 8 + rng.uniform(-1, 2))))))

            # monthly progress claims from start to today, ramping to target_actual
            months = max(1, (today - start).days // 30)
            for m in range(1, months + 1):
                frac = m / months
                pct = round(target_actual * frac, 1)
                claims.append(dict(
                    claim_id=f"{scode}-C{m}", subcontract_id=scode,
                    period_end=start + dt.timedelta(days=30 * m),
                    percent_complete=pct,
                    completed_value=round(contract * pct / 100.0),
                    note="progress claim"))
            sid += 1

    return projects, companies, subcontracts, sov_lines, claims


# ---- Material procurement -----------------------------------------------------
SUPPLIERS = [
    ("SUP-A", "Nile Building Supplies", "General"),
    ("SUP-B", "Delta Steel Co", "Steel"),
    ("SUP-C", "Cairo Cement", "Concrete"),
    ("SUP-D", "ProPaint Trading", "Finishing"),
    ("SUP-E", "PipeMax", "Plumbing"),
    ("SUP-F", "ElectroSupply", "Electrical"),
    ("SUP-G", "AggregateOne", "Aggregate"),
    ("SUP-H", "GlassWorks", "Glazing"),
]

MATERIALS = [
    ("M01", "Cement", "Concrete", "bag"), ("M02", "Steel Rebar", "Steel", "ton"),
    ("M03", "Bricks", "Masonry", "1000 pcs"), ("M04", "Paint", "Finishing", "liter"),
    ("M05", "Sand", "Aggregate", "m3"), ("M06", "Gravel", "Aggregate", "m3"),
    ("M07", "Timber", "Wood", "m3"), ("M08", "Glass Panels", "Glazing", "m2"),
    ("M09", "Ceramic Tiles", "Finishing", "m2"), ("M10", "PVC Pipes", "Plumbing", "m"),
    ("M11", "Electrical Cable", "Electrical", "m"), ("M12", "Insulation", "Finishing", "m2"),
    ("M13", "Concrete Blocks", "Masonry", "1000 pcs"), ("M14", "Gypsum Board", "Finishing", "m2"),
]


def generate_procurement(seed: int = 11):
    rng = random.Random(seed)
    today = dt.date.today()
    suppliers = [dict(supplier_id=s, name=n, category=c) for s, n, c in SUPPLIERS]
    materials = [dict(material_id=m, name=n, category=c, unit=u)
                 for m, n, c, u in MATERIALS]
    sup_reliable = {s: rng.uniform(0.72, 0.99) for s, _, _ in SUPPLIERS}
    sup_lead = {s: rng.randint(3, 16) for s, _, _ in SUPPLIERS}

    reqs, pos, lines, deliveries, invoices = [], [], [], [], []
    rid = poid = did = iid = 1
    for pid, _, _, status in PROJECTS:
        if status == "Planned":
            continue
        for mid, mname, mcat, unit in rng.sample(MATERIALS, rng.randint(4, 7)):
            required = round(rng.uniform(500, 12000))
            consumed = round(required * rng.uniform(0.2, 0.7))
            minimum = round(required * rng.uniform(0.15, 0.35))
            reqs.append(dict(req_id=f"R{rid:03d}", project_id=pid, material_id=mid,
                             required_qty=required, minimum_stock=minimum,
                             consumed_qty=consumed))
            rid += 1

            cand = [s for s in SUPPLIERS if s[2] == mcat] or SUPPLIERS
            sid = rng.choice(cand)[0]
            # order 50-110% of requirement across 1-2 POs
            to_order = round(required * rng.uniform(0.5, 1.1))
            npo = rng.choice([1, 1, 2])
            for k in range(npo):
                qty = round(to_order / npo)
                order_date = today - dt.timedelta(days=rng.randint(8, 140))
                lead = sup_lead[sid]
                expected = order_date + dt.timedelta(days=lead)
                price = round(rng.uniform(0.5, 700), 2)
                po_id = f"PO{poid:04d}"
                if today >= expected:                       # should have arrived
                    late = 0 if rng.random() < sup_reliable[sid] else rng.randint(2, 15)
                    recv = min(today, expected + dt.timedelta(days=late))
                    rejected = (round(qty * rng.uniform(0.01, 0.07))
                                if rng.random() > sup_reliable[sid] else 0)
                    deliveries.append(dict(
                        delivery_id=f"D{did:04d}", po_id=po_id, material_id=mid,
                        project_id=pid, qty_received=qty, qty_rejected=rejected,
                        order_date=order_date, expected_date=expected,
                        received_date=recv))
                    did += 1
                    st = "Received"
                    if rng.random() < 0.7:                   # supplier invoiced
                        over = rng.random() < 0.15
                        bqty = round(qty * 1.12) if over else qty - rejected
                        invoices.append(dict(
                            invoice_id=f"INV{iid:04d}", po_id=po_id, supplier_id=sid,
                            invoice_date=recv, billed_qty=bqty,
                            amount=round(bqty * price),
                            status="Exception" if over else "Matched"))
                        iid += 1
                else:
                    st = "Open"                             # still in transit
                pos.append(dict(po_id=po_id, supplier_id=sid, project_id=pid,
                                order_date=order_date, expected_delivery=expected,
                                status=st))
                lines.append(dict(line_id=f"{po_id}-L1", po_id=po_id,
                                  material_id=mid, qty_ordered=qty, unit_price=price))
                poid += 1
    return suppliers, materials, reqs, pos, lines, deliveries, invoices
