
import streamlit as st
import pandas as pd
import sqlite3
from datetime import date, datetime
import io, os

st.set_page_config(page_title="RRM Rice Mill Tracker", layout="wide")

# ---------- Storage (works on Streamlit Cloud) ----------
DATA_DIR = os.path.join(os.getcwd(), "data")
os.makedirs(DATA_DIR, exist_ok=True)
DB_PATH = os.path.join(DATA_DIR, "rrm_tracker.db")
KG_PER_QTL_DEFAULT = 100

# ---------- DB helpers ----------
def get_conn():
    return sqlite3.connect(DB_PATH, check_same_thread=False)

def init_db():
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("CREATE TABLE IF NOT EXISTS config (key TEXT PRIMARY KEY, value TEXT)")
        cur.execute("CREATE TABLE IF NOT EXISTS paddy_types (paddy_id TEXT PRIMARY KEY, paddy_name TEXT UNIQUE)")
        cur.execute("""CREATE TABLE IF NOT EXISTS rice_grades (
                        grade_id TEXT PRIMARY KEY, grade_name TEXT UNIQUE, default_price_qtl REAL DEFAULT 0)""")
        cur.execute("""CREATE TABLE IF NOT EXISTS purchases (
                        id INTEGER PRIMARY KEY AUTOINCREMENT, dt TEXT, paddy_id TEXT,
                        qty_qtl REAL, qty_kg REAL, final_qtl REAL, rate_qtl REAL, cost REAL, notes TEXT)""")
        cur.execute("""CREATE TABLE IF NOT EXISTS milling_input (
                        id INTEGER PRIMARY KEY AUTOINCREMENT, dt TEXT, paddy_id TEXT,
                        used_qtl REAL, used_kg REAL, final_used_qtl REAL,
                        husk_qtl REAL, polish_qtl REAL, expense REAL, notes TEXT)""")
        cur.execute("""CREATE TABLE IF NOT EXISTS milling_output (
                        id INTEGER PRIMARY KEY AUTOINCREMENT, dt TEXT, paddy_id TEXT, grade_id TEXT,
                        out_qtl REAL, out_kg REAL, final_out_qtl REAL, notes TEXT)""")
        cur.execute("""CREATE TABLE IF NOT EXISTS sales (
                        id INTEGER PRIMARY KEY AUTOINCREMENT, dt TEXT, product TEXT, grade_id TEXT,
                        qty_qtl REAL, qty_kg REAL, final_qtl REAL, rate_qtl REAL, revenue REAL, notes TEXT)""")
        conn.commit()
        cur.execute("INSERT OR IGNORE INTO config(key,value) VALUES('kg_per_qtl',?)", (str(KG_PER_QTL_DEFAULT),))
        # seeds
        cur.execute("INSERT OR IGNORE INTO paddy_types(paddy_id,paddy_name) VALUES('PAD-1121','1121'),('PAD-1509','1509'),('PAD-PR14','PR-14')")
        cur.execute("""INSERT OR IGNORE INTO rice_grades(grade_id,grade_name,default_price_qtl) VALUES
            ('GRD-WAND','Wand',0),('GRD-S2ND','Super 2nd Wand',0),('GRD-2ND','2nd Wand',0),
            ('GRD-TIBAR','Tibar',0),('GRD-SDUB','Super Dubar',0),('GRD-DUB','Dubar',0),
            ('GRD-MDUB','Mini Dubar',0),('GRD-SMOG','Super Mogara',0),('GRD-MOG','Mogara',0),
            ('GRD-MMOG','Mini Mogara',0)""")
        conn.commit()

def df_read(sql, params=()):
    with get_conn() as conn:
        return pd.read_sql_query(sql, conn, params=params)

def exec_sql(sql, params=()):
    with get_conn() as conn:
        conn.execute(sql, params)
        conn.commit()

def to_date(s):
    try:
        return datetime.strptime(s, "%Y-%m-%d").date()
    except:
        return None

# Initialize DB
init_db()

# ---------- UI settings ----------
st.title("🌾 Rajendra Rice & General Mills — Rice Mill Tracker (Cloud)")
st.sidebar.header("Settings")

# robust read of KG per quintal
try:
    cfg_df = df_read("SELECT value FROM config WHERE key='kg_per_qtl'")
    _kg = int(float(cfg_df["value"].iloc[0])) if not cfg_df.empty else KG_PER_QTL_DEFAULT
except Exception:
    _kg = KG_PER_QTL_DEFAULT
kg_per_qtl = st.sidebar.number_input("KG per Quintal", min_value=1, max_value=200, value=_kg)

mobile_mode = st.sidebar.toggle("Mobile layout (stacked forms)", value=True)
if st.sidebar.button("Save Conversion"):
    exec_sql("INSERT OR REPLACE INTO config(key,value) VALUES('kg_per_qtl',?)", (int(kg_per_qtl),))
    st.sidebar.success("Saved")

st.sidebar.markdown("---")
st.sidebar.subheader("Export")
if st.sidebar.button("Export all data (.xlsx)"):
    with get_conn() as conn:
        xls = io.BytesIO()
        with pd.ExcelWriter(xls, engine="xlsxwriter") as writer:
            for name in ["paddy_types","rice_grades","purchases","milling_input","milling_output","sales"]:
                pd.read_sql_query(f"SELECT * FROM {name}", conn).to_excel(writer, sheet_name=name, index=False)
        st.sidebar.download_button("Download RRM_Data.xlsx", xls.getvalue(), file_name="RRM_Data.xlsx")

# ---------- Helper to layout forms (fixed) ----------
def cols(n:int):
    """Return a list of n column-like containers.
       In mobile mode, return n separate full-width containers stacked vertically,
       so callers can always unpack: c1, c2 = cols(2), etc."""
    if mobile_mode:
        # Create n independent single columns (stacked vertically)
        return [st.columns(1)[0] for _ in range(n)]
    else:
        return list(st.columns(n))

# ---------- Tabs ----------
tab_dash, tab_masters, tab_pur, tab_mi, tab_mo, tab_sales, tab_stock, tab_yield = st.tabs([
    "Dashboard","Masters","Purchases","Milling Input","Milling Output","Sales","Stock Ledger","Yield % Report"
])

# ----- Dashboard -----
with tab_dash:
    c1, c2, c3 = st.columns(3)
    sales_rev = df_read("SELECT COALESCE(SUM(revenue),0) AS v FROM sales")["v"][0]
    pur_cost  = df_read("SELECT COALESCE(SUM(cost),0) AS v FROM purchases")["v"][0]
    mil_exp   = df_read("SELECT COALESCE(SUM(expense),0) AS v FROM milling_input")["v"][0]
    gross     = sales_rev - pur_cost - mil_exp
    c1.metric("Sales Revenue (₹)", f"{sales_rev:,.0f}")
    c2.metric("Paddy Cost (₹)", f"{pur_cost:,.0f}")
    c3.metric("Gross Profit (₹)", f"{gross:,.0f}")

# ----- Masters -----
with tab_masters:
    st.subheader("Paddy Types")
    paddy = df_read("SELECT paddy_id AS ID, paddy_name AS Name FROM paddy_types ORDER BY Name")
    st.dataframe(paddy, use_container_width=True)
    with st.expander("Add / Rename / Delete"):
        action = st.radio("Action", ["Add","Rename","Delete"], horizontal=True, key="pad_action")
        if action == "Add":
            pid = st.text_input("Paddy ID (e.g. PAD-1718)")
            pname = st.text_input("Paddy Name")
            if st.button("Add Paddy"):
                exec_sql("INSERT INTO paddy_types(paddy_id,paddy_name) VALUES(?,?)", (pid, pname))
                st.success("Added"); st.rerun()
        elif action == "Rename":
            if not paddy.empty:
                sel = st.selectbox("Choose", paddy["ID"])
                new = st.text_input("New Name")
                if st.button("Rename Paddy"):
                    exec_sql("UPDATE paddy_types SET paddy_name=? WHERE paddy_id=?", (new, sel))
                    st.success("Updated"); st.rerun()
        else:
            if not paddy.empty:
                sel = st.selectbox("Delete Paddy", paddy["ID"])
                if st.button("Confirm Delete"):
                    exec_sql("DELETE FROM paddy_types WHERE paddy_id=?", (sel,))
                    st.warning("Deleted"); st.rerun()

    st.markdown("---")
    st.subheader("Rice Grades / Cuts")
    grades = df_read("SELECT grade_id AS ID, grade_name AS Name, default_price_qtl AS DefaultPrice FROM rice_grades ORDER BY Name")
    st.dataframe(grades, use_container_width=True)
    with st.expander("Add / Edit Price / Delete"):
        gact = st.radio("Action", ["Add","Edit Price","Delete"], horizontal=True, key="grade_action")
        if gact == "Add":
            gid = st.text_input("Grade ID")
            gname = st.text_input("Grade Name")
            if st.button("Add Grade"):
                exec_sql("INSERT INTO rice_grades(grade_id,grade_name,default_price_qtl) VALUES(?,?,0)", (gid, gname))
                st.success("Added"); st.rerun()
        elif gact == "Edit Price":
            if not grades.empty:
                sel = st.selectbox("Grade", grades["ID"])
                price = st.number_input("Default Price (₹/qtl)", min_value=0.0, step=50.0)
                if st.button("Update Price"):
                    exec_sql("UPDATE rice_grades SET default_price_qtl=? WHERE grade_id=?", (price, sel))
                    st.success("Updated"); st.rerun()
        else:
            if not grades.empty:
                sel = st.selectbox("Delete Grade", grades["ID"])
                if st.button("Confirm Delete Grade"):
                    exec_sql("DELETE FROM rice_grades WHERE grade_id=?", (sel,))
                    st.warning("Deleted"); st.rerun()

# ----- Purchases -----
with tab_pur:
    st.subheader("🛒 Purchases")
    c1, c2 = cols(2)
    dfrom = c1.date_input("From", value=date(2025,1,1), key="pur_from")
    dto   = c2.date_input("To", value=date.today(), key="pur_to")
    pdata = df_read("SELECT id, dt, paddy_id, final_qtl, rate_qtl, cost, notes FROM purchases ORDER BY id DESC")
    pdata["Date"] = pdata["dt"].apply(lambda s: to_date(s))
    mask = (pdata["Date"]>=dfrom) & (pdata["Date"]<=dto)
    pdata_f = pdata.loc[mask].copy()
    st.dataframe(pdata_f.drop(columns=["dt"]), use_container_width=True, height=280)

    st.markdown("**Add New**")
    paddy_list = df_read("SELECT paddy_id, paddy_name FROM paddy_types ORDER BY paddy_name")
    a1, a2, a3, a4 = cols(4)
    dt_new = a1.date_input("Date", value=date.today(), key="pur_dt2")
    pid = a2.selectbox("Paddy", paddy_list["paddy_id"], format_func=lambda x: paddy_list.set_index("paddy_id").loc[x,"paddy_name"])
    qty = a3.number_input("Qty (qtl)", min_value=0.0, step=0.1, key="pur_qty2")
    rate = a4.number_input("Rate (₹/qtl)", min_value=0.0, step=50.0, key="pur_rate2")
    notes = st.text_input("Notes", key="pur_notes2")
    if st.button("Add Purchase", key="pur_add_btn2"):
        cost = qty*rate
        exec_sql("""INSERT INTO purchases(dt,paddy_id,qty_qtl,qty_kg,final_qtl,rate_qtl,cost,notes)
                    VALUES(?,?,?,?,?,?,?,?)""", (dt_new.isoformat(), pid, qty, 0, qty, rate, cost, notes))
        st.success("Added"); st.rerun()

    st.markdown("---"); st.markdown("**Edit / Delete**")
    if not pdata_f.empty:
        row_id = st.selectbox("Select Purchase ID", pdata_f["id"], key="pur_row")
        row = pdata_f[pdata_f["id"]==row_id].iloc[0]
        e1, e2, e3 = cols(3)
        new_qty = e1.number_input("Qty (qtl)", value=float(row["final_qtl"]), step=0.1, key="pur_edit_qty2")
        new_rate = e2.number_input("Rate (₹/qtl)", value=float(row["rate_qtl"]), step=50.0, key="pur_edit_rate2")
        new_notes = e3.text_input("Notes", value=row["notes"] or "", key="pur_edit_notes2")
        if st.button("Save Changes", key="pur_save2"):
            new_cost = new_qty*new_rate
            exec_sql("UPDATE purchases SET final_qtl=?, rate_qtl=?, cost=?, notes=? WHERE id=?",
                     (new_qty, new_rate, new_cost, new_notes, int(row_id)))
            st.success("Updated"); st.rerun()
        if st.button("🗑️ Delete Purchase", key="pur_del2"):
            exec_sql("DELETE FROM purchases WHERE id=?", (int(row_id),))
            st.warning("Deleted"); st.rerun()

# ----- Milling Input -----
with tab_mi:
    st.subheader("⚙️ Milling Input")
    c1, c2 = cols(2)
    dfrom = c1.date_input("From ", value=date(2025,1,1), key="mi_from2")
    dto   = c2.date_input("To ", value=date.today(), key="mi_to2")
    tdf = df_read("SELECT id, dt, paddy_id, final_used_qtl, husk_qtl, polish_qtl, expense, notes FROM milling_input ORDER BY id DESC")
    tdf["Date"] = tdf["dt"].apply(lambda s: to_date(s))
    tdf = tdf[(tdf["Date"]>=dfrom) & (tdf["Date"]<=dto)]
    st.dataframe(tdf.drop(columns=["dt"]), use_container_width=True, height=280)

    st.markdown("**Add New**")
    paddy_list2 = df_read("SELECT paddy_id, paddy_name FROM paddy_types ORDER BY paddy_name")
    a1, a2, a3 = cols(3)
    mi_dt = a1.date_input("Date", value=date.today(), key="mi_add_dt2")
    mi_pid = a2.selectbox("Paddy", paddy_list2["paddy_id"], format_func=lambda x: paddy_list2.set_index("paddy_id").loc[x,"paddy_name"], key="mi_add_pid2")
    mi_used = a3.number_input("Used (qtl)", min_value=0.0, step=0.1, key="mi_add_used2")
    b1, b2, b3 = cols(3)
    mi_husk = b1.number_input("Husk (qtl)", min_value=0.0, step=0.1, key="mi_add_husk2")
    mi_pol  = b2.number_input("Polish (qtl)", min_value=0.0, step=0.1, key="mi_add_pol2")
    mi_exp  = b3.number_input("Expense (₹)", min_value=0.0, step=100.0, key="mi_add_exp2")
    mi_notes = st.text_input("Notes", key="mi_add_notes2")
    if st.button("Add Milling Input", key="mi_add_btn2"):
        exec_sql("INSERT INTO milling_input(dt,paddy_id,used_qtl,used_kg,final_used_qtl,husk_qtl,polish_qtl,expense,notes) VALUES(?,?,?,?,?,?,?,?,?)",
                 (mi_dt.isoformat(), mi_pid, mi_used, 0, mi_used, mi_husk, mi_pol, mi_exp, mi_notes))
        st.success("Added"); st.rerun()

    st.markdown("---")
    if not tdf.empty:
        row_id = st.selectbox("Select MI ID", tdf["id"], key="mi_row2")
        row = tdf[tdf["id"]==row_id].iloc[0]
        e1, e2, e3, e4 = cols(4)
        used = e1.number_input("Used (qtl)", value=float(row["final_used_qtl"]), step=0.1, key="mi_edit_used2")
        husk = e2.number_input("Husk (qtl)", value=float(row["husk_qtl"] or 0), step=0.1, key="mi_edit_husk2")
        polish = e3.number_input("Polish (qtl)", value=float(row["polish_qtl"] or 0), step=0.1, key="mi_edit_pol2")
        exp = e4.number_input("Expense (₹)", value=float(row["expense"] or 0), step=100.0, key="mi_edit_exp2")
        notes = st.text_input("Notes", value=row["notes"] or "", key="mi_edit_notes2")
        if st.button("Save Changes", key="mi_save2"):
            exec_sql("UPDATE milling_input SET final_used_qtl=?, husk_qtl=?, polish_qtl=?, expense=?, notes=? WHERE id=?",
                     (used, husk, polish, exp, notes, int(row_id)))
            st.success("Updated"); st.rerun()
        if st.button("🗑️ Delete", key="mi_del2"):
            exec_sql("DELETE FROM milling_input WHERE id=?", (int(row_id),))
            st.warning("Deleted"); st.rerun()

# ----- Milling Output -----
with tab_mo:
    st.subheader("📦 Milling Output (ANY Paddy × ANY Grade)")
    c1, c2, c3 = cols(3)
    dfrom = c1.date_input("From  ", value=date(2025,1,1), key="mo_from2")
    dto   = c2.date_input("To  ", value=date.today(), key="mo_to2")
    grade_filter = c3.text_input("Filter by Grade (name contains)", key="mo_grade_f2")
    mdf = df_read("""SELECT mo.id, mo.dt, mo.paddy_id, g.grade_name, mo.final_out_qtl, mo.notes
                     FROM milling_output mo LEFT JOIN rice_grades g ON mo.grade_id=g.grade_id
                     ORDER BY mo.id DESC""")
    mdf["Date"] = mdf["dt"].apply(lambda s: to_date(s))
    mdf = mdf[(mdf["Date"]>=dfrom) & (mdf["Date"]<=dto)]
    if grade_filter:
        mdf = mdf[mdf["grade_name"].fillna("").str.contains(grade_filter, case=False)]
    st.dataframe(mdf.drop(columns=["dt"]), use_container_width=True, height=280)

    st.markdown("**Add New**")
    paddy_list3 = df_read("SELECT paddy_id, paddy_name FROM paddy_types ORDER BY paddy_name")
    grade_list3 = df_read("SELECT grade_id, grade_name FROM rice_grades ORDER BY grade_name")
    a1, a2, a3 = cols(3)
    mo_dt = a1.date_input("Date", value=date.today(), key="mo_add_dt2")
    mo_pid = a2.selectbox("Paddy", paddy_list3["paddy_id"], format_func=lambda x: paddy_list3.set_index("paddy_id").loc[x,"paddy_name"], key="mo_add_pid2")
    mo_gid = a3.selectbox("Grade", grade_list3["grade_id"], format_func=lambda x: grade_list3.set_index("grade_id").loc[x,"grade_name"], key="mo_add_gid2")
    b1, b2 = cols(2)
    mo_qty = b1.number_input("Rice OUT (qtl)", min_value=0.0, step=0.1, key="mo_add_qty2")
    mo_notes = b2.text_input("Notes", key="mo_add_notes2")
    if st.button("Add Milling Output", key="mo_add_btn2"):
        exec_sql("INSERT INTO milling_output(dt,paddy_id,grade_id,out_qtl,out_kg,final_out_qtl,notes) VALUES(?,?,?,?,?,?,?)",
                 (mo_dt.isoformat(), mo_pid, mo_gid, mo_qty, 0, mo_qty, mo_notes))
        st.success("Added"); st.rerun()

    st.markdown("---")
    if not mdf.empty:
        row_id = st.selectbox("Select MO ID", mdf["id"], key="mo_row2")
        row = mdf[mdf["id"]==row_id].iloc[0]
        e1, e2 = cols(2)
        qty = e1.number_input("Out (qtl)", value=float(row["final_out_qtl"]), step=0.1, key="mo_edit_qty2")
        notes = e2.text_input("Notes", value=row["notes"] or "", key="mo_edit_notes2")
        if st.button("Save Changes", key="mo_save2"):
            exec_sql("UPDATE milling_output SET final_out_qtl=?, notes=? WHERE id=?", (qty, notes, int(row_id)))
            st.success("Updated"); st.rerun()
        if st.button("🗑️ Delete", key="mo_del2"):
            exec_sql("DELETE FROM milling_output WHERE id=?", (int(row_id),))
            st.warning("Deleted"); st.rerun()

# ----- Sales -----
with tab_sales:
    st.subheader("🧾 Sales")
    c1, c2, c3 = cols(3)
    dfrom = c1.date_input("From   ", value=date(2025,1,1), key="sa_from2")
    dto   = c2.date_input("To   ", value=date.today(), key="sa_to2")
    prod  = c3.selectbox("Product filter", ["All","Rice","Husk","Polish"], key="sa_prod2")
    sdf = df_read("""SELECT s.id, s.dt, s.product, g.grade_name, s.final_qtl, s.rate_qtl, s.revenue, s.notes
                     FROM sales s LEFT JOIN rice_grades g ON s.grade_id=g.grade_id
                     ORDER BY s.id DESC""")
    sdf["Date"] = sdf["dt"].apply(lambda s: to_date(s))
    sdf = sdf[(sdf["Date"]>=dfrom) & (sdf["Date"]<=dto)]
    if prod!="All":
        sdf = sdf[sdf["product"]==prod]
    st.dataframe(sdf.drop(columns=["dt"]), use_container_width=True, height=280)

    st.markdown("**Add New**")
    grade_list4 = df_read("SELECT grade_id, grade_name, default_price_qtl FROM rice_grades ORDER BY grade_name")
    a1, a2, a3 = cols(3)
    sa_dt = a1.date_input("Date", value=date.today(), key="sa_add_dt2")
    sa_prod = a2.selectbox("Product", ["Rice","Husk","Polish"], key="sa_add_prod2")
    sa_gid = a3.selectbox("Grade (if Rice)", options=[""] + grade_list4["grade_id"].tolist(), index=0,
                             format_func=lambda x: (grade_list4.set_index("grade_id").loc[x,"grade_name"] if x else ""), key="sa_add_gid2")
    b1, b2, b3 = cols(3)
    sa_qty = b1.number_input("Qty (qtl)", min_value=0.0, step=0.1, key="sa_add_qty2")
    # default price
    def_rate = 0.0
    try:
        if sa_prod == "Rice" and sa_gid:
            def_rate = float(grade_list4.set_index("grade_id").loc[sa_gid,"default_price_qtl"] or 0.0)
    except Exception:
        def_rate = 0.0
    sa_rate = b2.number_input("Rate (₹/qtl)", min_value=0.0, step=50.0, value=def_rate, key="sa_add_rate2")
    sa_notes = b3.text_input("Notes", key="sa_add_notes2")
    if st.button("Add Sale", key="sa_add_btn2"):
        revenue = sa_qty * sa_rate if (sa_qty and sa_rate) else 0.0
        exec_sql("INSERT INTO sales(dt,product,grade_id,qty_qtl,qty_kg,final_qtl,rate_qtl,revenue,notes) VALUES(?,?,?,?,?,?,?,?,?)",
                 (sa_dt.isoformat(), sa_prod, (sa_gid if sa_prod=='Rice' and sa_gid else None),
                  sa_qty, 0, sa_qty, sa_rate, revenue, sa_notes))
        st.success("Added"); st.rerun()

    st.markdown("---")
    if not sdf.empty:
        row_id = st.selectbox("Select Sale ID", sdf["id"], key="sa_row2")
        row = sdf[sdf["id"]==row_id].iloc[0]
        e1, e2, e3 = cols(3)
        qty = e1.number_input("Qty (qtl)", value=float(row["final_qtl"]), step=0.1, key="sa_edit_qty2")
        rate = e2.number_input("Rate (₹/qtl)", value=float(row["rate_qtl"] or 0), step=50.0, key="sa_edit_rate2")
        notes = e3.text_input("Notes", value=row["notes"] or "", key="sa_edit_notes2")
        if st.button("Save Changes", key="sa_save2"):
            revenue = qty*(rate or 0)
            exec_sql("UPDATE sales SET final_qtl=?, rate_qtl=?, revenue=?, notes=? WHERE id=?",
                     (qty, rate, revenue, notes, int(row_id)))
            st.success("Updated"); st.rerun()
        if st.button("🗑️ Delete", key="sa_del2"):
            exec_sql("DELETE FROM sales WHERE id=?", (int(row_id),))
            st.warning("Deleted"); st.rerun()

# ----- Stock Ledger -----
with tab_stock:
    st.subheader("📒 Stock Ledger")
    paddy_in = df_read("SELECT paddy_id, COALESCE(SUM(final_qtl),0) AS in_qtl FROM purchases GROUP BY paddy_id")
    paddy_used = df_read("SELECT paddy_id, COALESCE(SUM(final_used_qtl),0) AS used_qtl FROM milling_input GROUP BY paddy_id")
    paddy_bal = pd.merge(paddy_in, paddy_used, on="paddy_id", how="outer").fillna(0)
    paddy_bal["Closing_qtl"] = paddy_bal["in_qtl"] - paddy_bal["used_qtl"]
    names = df_read("SELECT paddy_id, paddy_name FROM paddy_types")
    paddy_bal = paddy_bal.merge(names, on="paddy_id", how="left")
    paddy_bal = paddy_bal[["paddy_name","in_qtl","used_qtl","Closing_qtl"]].rename(columns={"paddy_name":"Paddy"})
    st.markdown("**Paddy Stock (qtl)**")
    st.dataframe(paddy_bal, use_container_width=True)

    out = df_read("SELECT grade_id, COALESCE(SUM(final_out_qtl),0) AS out_qtl FROM milling_output GROUP BY grade_id")
    sold = df_read("SELECT grade_id, COALESCE(SUM(final_qtl),0) AS sold_qtl FROM sales WHERE product='Rice' GROUP BY grade_id")
    grade_bal = pd.merge(out, sold, on="grade_id", how="outer").fillna(0)
    grade_bal["Closing_qtl"] = grade_bal["out_qtl"] - grade_bal["sold_qtl"]
    gnames = df_read("SELECT grade_id, grade_name FROM rice_grades")
    grade_bal = grade_bal.merge(gnames, on="grade_id", how="left")
    grade_bal = grade_bal[["grade_name","out_qtl","sold_qtl","Closing_qtl"]].rename(columns={"grade_name":"Grade"})
    st.markdown("**Rice Grade Stock (qtl)**")
    st.dataframe(grade_bal, use_container_width=True)

# ----- Yield % Report -----
with tab_yield:
    st.subheader("📊 Yield % Report")
    out_by_paddy = df_read("SELECT paddy_id, COALESCE(SUM(final_out_qtl),0) AS rice_out_qtl FROM milling_output GROUP BY paddy_id")
    used_by_paddy = df_read("SELECT paddy_id, COALESCE(SUM(final_used_qtl),0) AS paddy_used_qtl FROM milling_input GROUP BY paddy_id")
    y = pd.merge(used_by_paddy, out_by_paddy, on="paddy_id", how="outer").fillna(0)
    names = df_read("SELECT paddy_id, paddy_name FROM paddy_types")
    y = y.merge(names, on="paddy_id", how="left")
    y["rice_out_qtl"] = pd.to_numeric(y["rice_out_qtl"], errors="coerce")
    y["paddy_used_qtl"] = pd.to_numeric(y["paddy_used_qtl"], errors="coerce")
    y["Yield_%"] = (y["rice_out_qtl"] * 100.0 / y["paddy_used_qtl"].replace({0: pd.NA})).round(2)
    y = y[["paddy_name","paddy_used_qtl","rice_out_qtl","Yield_%"]].rename(columns={"paddy_name":"Paddy","paddy_used_qtl":"Paddy Used (qtl)","rice_out_qtl":"Rice Out (qtl)"})
    st.markdown("**Overall Yield by Paddy Type**")
    st.dataframe(y, use_container_width=True)

    mi_df = df_read("SELECT dt, final_used_qtl FROM milling_input").copy()
    mo_df = df_read("SELECT dt, final_out_qtl FROM milling_output").copy()
    mi_df["dt"] = pd.to_datetime(mi_df["dt"], errors="coerce").dt.date
    mi_df["final_used_qtl"] = pd.to_numeric(mi_df["final_used_qtl"], errors="coerce")
    mo_df["dt"] = pd.to_datetime(mo_df["dt"], errors="coerce").dt.date
    mo_df["final_out_qtl"] = pd.to_numeric(mo_df["final_out_qtl"], errors="coerce")
    mi_g = mi_df.groupby("dt", dropna=True)["final_used_qtl"].sum().rename("Paddy_Used_qtl")
    mo_g = mo_df.groupby("dt", dropna=True)["final_out_qtl"].sum().rename("Rice_Out_qtl")
    dy = pd.concat([mi_g, mo_g], axis=1).fillna(0.0).reset_index().rename(columns={"dt":"Date"})
    if not dy.empty:
        dy["Yield_%"] = (dy["Rice_Out_qtl"] * 100.0 / dy["Paddy_Used_qtl"].replace({0: pd.NA})).round(2)
        dy = dy.sort_values("Date", ascending=False)
    st.markdown("**Daily Yield (All Paddies)**")
    st.dataframe(dy, use_container_width=True, height=280)
