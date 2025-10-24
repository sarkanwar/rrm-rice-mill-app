
import streamlit as st
import pandas as pd
import sqlite3
from datetime import date, timedelta
import io

st.set_page_config(page_title="RRM Rice Mill Tracker", layout="wide")

DB_PATH = "rrm_tracker.db"
KG_PER_QTL_DEFAULT = 100

# ----------------- DB Helpers -----------------
def get_conn():
    return sqlite3.connect(DB_PATH, check_same_thread=False)

def init_db():
    conn = get_conn()
    cur = conn.cursor()
    # Config
    cur.execute("""CREATE TABLE IF NOT EXISTS config (
        key TEXT PRIMARY KEY,
        value TEXT
    )""")
    # Masters
    cur.execute("""CREATE TABLE IF NOT EXISTS paddy_types (
        paddy_id TEXT PRIMARY KEY,
        paddy_name TEXT UNIQUE
    )""")
    cur.execute("""CREATE TABLE IF NOT EXISTS rice_grades (
        grade_id TEXT PRIMARY KEY,
        grade_name TEXT UNIQUE,
        default_price_qtl REAL DEFAULT 0
    )""")
    # Transactions
    cur.execute("""CREATE TABLE IF NOT EXISTS purchases (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        dt TEXT,
        paddy_id TEXT,
        qty_qtl REAL,
        qty_kg REAL,
        final_qtl REAL,
        rate_qtl REAL,
        cost REAL,
        notes TEXT
    )""")
    cur.execute("""CREATE TABLE IF NOT EXISTS milling_input (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        dt TEXT,
        paddy_id TEXT,
        used_qtl REAL,
        used_kg REAL,
        final_used_qtl REAL,
        husk_qtl REAL,
        polish_qtl REAL,
        expense REAL,
        notes TEXT
    )""")
    cur.execute("""CREATE TABLE IF NOT EXISTS milling_output (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        dt TEXT,
        paddy_id TEXT,
        grade_id TEXT,
        out_qtl REAL,
        out_kg REAL,
        final_out_qtl REAL,
        notes TEXT
    )""")
    cur.execute("""CREATE TABLE IF NOT EXISTS sales (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        dt TEXT,
        product TEXT,
        grade_id TEXT,
        qty_qtl REAL,
        qty_kg REAL,
        final_qtl REAL,
        rate_qtl REAL,
        revenue REAL,
        notes TEXT
    )""")
    conn.commit()
    # Seed config
    cur.execute("INSERT OR IGNORE INTO config(key,value) VALUES('kg_per_qtl',?)", (str(KG_PER_QTL_DEFAULT),))
    # Seed masters minimal
    cur.execute("INSERT OR IGNORE INTO paddy_types(paddy_id,paddy_name) VALUES('PAD-1121','1121'),('PAD-1509','1509'),('PAD-PR14','PR-14')")
    cur.execute("""INSERT OR IGNORE INTO rice_grades(grade_id,grade_name,default_price_qtl) VALUES
        ('GRD-WAND','Wand',0),('GRD-S2ND','Super 2nd Wand',0),('GRD-2ND','2nd Wand',0),
        ('GRD-TIBAR','Tibar',0),('GRD-SDUB','Super Dubar',0),('GRD-DUB','Dubar',0),
        ('GRD-MDUB','Mini Dubar',0),('GRD-SMOG','Super Mogara',0),('GRD-MOG','Mogara',0),
        ('GRD-MMOG','Mini Mogara',0)
    """)
    conn.commit()
    conn.close()

def get_cfg(key, default=None):
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("SELECT value FROM config WHERE key=?", (key,))
        r = cur.fetchone()
        return r[0] if r else default

def set_cfg(key, value):
    with get_conn() as conn:
        conn.execute("INSERT OR REPLACE INTO config(key,value) VALUES(?,?)", (key, str(value)))

def df_read(sql, params=()):
    with get_conn() as conn:
        return pd.read_sql_query(sql, conn, params=params)

def exec_sql(sql, params=()):
    with get_conn() as conn:
        conn.execute(sql, params)
        conn.commit()

# Initialize
init_db()

st.title("Rajendra Rice & General Mills — Rice Mill Tracker")

# Sidebar
st.sidebar.header("Settings & Data")
kg_per_qtl = st.sidebar.number_input("KG per Quintal", min_value=1, max_value=200, value=int(get_cfg("kg_per_qtl", KG_PER_QTL_DEFAULT)))
if st.sidebar.button("Save Conversion"):
    set_cfg("kg_per_qtl", kg_per_qtl)
    st.sidebar.success("Saved")

# Tabs
tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs(["Dashboard","Masters","Purchases","Milling Input","Milling Output","Sales"])

# -------- Dashboard --------
with tab1:
    colA, colB, colC = st.columns([1,1,1])
    sales_rev = df_read("SELECT COALESCE(SUM(revenue),0) AS r FROM sales")["r"][0]
    pur_cost = df_read("SELECT COALESCE(SUM(cost),0) AS c FROM purchases")["c"][0]
    mil_exp = df_read("SELECT COALESCE(SUM(expense),0) AS e FROM milling_input")["e"][0]
    gross_profit = sales_rev - pur_cost - mil_exp

    colA.metric("Sales Revenue (₹)", f"{sales_rev:,.0f}")
    colB.metric("Paddy Cost (₹)", f"{pur_cost:,.0f}")
    colC.metric("Gross Profit (₹)", f"{gross_profit:,.0f}")

    # Daily summary
    st.subheader("Daily Summary")
    daily = df_read("""
        SELECT dt as Date,
               COALESCE((SELECT SUM(final_qtl) FROM purchases p WHERE p.dt = s.dt),0) AS Paddy_IN_qtl,
               COALESCE((SELECT SUM(final_used_qtl) FROM milling_input mi WHERE mi.dt = s.dt),0) AS Paddy_USED_qtl,
               COALESCE((SELECT SUM(final_out_qtl) FROM milling_output mo WHERE mo.dt = s.dt),0) AS Rice_OUT_qtl,
               COALESCE((SELECT SUM(final_qtl) FROM sales sa WHERE sa.dt = s.dt AND product='Rice'),0) AS Rice_Sold_qtl,
               COALESCE((SELECT SUM(revenue) FROM sales sa WHERE sa.dt = s.dt),0) AS Sales_Revenue
        FROM (
            SELECT dt FROM purchases
            UNION
            SELECT dt FROM milling_input
            UNION
            SELECT dt FROM milling_output
            UNION
            SELECT dt FROM sales
        ) s
        WHERE dt IS NOT NULL AND dt<>''
        GROUP BY dt
        ORDER BY dt DESC
    """)
    st.dataframe(daily, use_container_width=True)

# -------- Masters --------
with tab2:
    st.subheader("Paddy Types")
    paddy = df_read("SELECT paddy_id AS ID, paddy_name AS Name FROM paddy_types ORDER BY Name")
    st.dataframe(paddy, use_container_width=True)
    with st.expander("Add / Rename Paddy Type"):
        mode = st.radio("Action", ["Add","Rename"], horizontal=True)
        if mode=="Add":
            pid = st.text_input("Paddy ID (e.g., PAD-1718)")
            pname = st.text_input("Paddy Name (e.g., 1718)")
            if st.button("Add Paddy Type"):
                if pid and pname:
                    try:
                        exec_sql("INSERT INTO paddy_types(paddy_id,paddy_name) VALUES(?,?)", (pid, pname))
                        st.success("Added")
                    except Exception as e:
                        st.error(f"Error: {e}")
        else:
            if not paddy.empty:
                old = st.selectbox("Select existing", paddy["ID"].tolist())
                new_name = st.text_input("New Name")
                if st.button("Rename"):
                    try:
                        exec_sql("UPDATE paddy_types SET paddy_name=? WHERE paddy_id=?", (new_name, old))
                        st.success("Renamed")
                    except Exception as e:
                        st.error(f"Error: {e}")

    st.markdown("---")
    st.subheader("Rice Grades / Cuts")
    grades = df_read("SELECT grade_id AS ID, grade_name AS Name, default_price_qtl AS DefaultPrice FROM rice_grades ORDER BY Name")
    st.dataframe(grades, use_container_width=True)

    with st.expander("Add / Edit Grade"):
        modeg = st.radio("Action", ["Add","Edit Price"], horizontal=True)
        if modeg=="Add":
            gid = st.text_input("Grade ID (e.g., GRD-DUBAR2)")
            gname = st.text_input("Grade Name")
            if st.button("Add Grade"):
                if gid and gname:
                    try:
                        exec_sql("INSERT INTO rice_grades(grade_id,grade_name,default_price_qtl) VALUES(?,?,0)", (gid, gname))
                        st.success("Added")
                    except Exception as e:
                        st.error(f"Error: {e}")
        else:
            if not grades.empty:
                gid_sel = st.selectbox("Select Grade", grades["ID"].tolist())
                new_price = st.number_input("Default Price (₹/qtl)", min_value=0.0, value=0.0, step=50.0)
                if st.button("Update Price"):
                    try:
                        exec_sql("UPDATE rice_grades SET default_price_qtl=? WHERE grade_id=?", (new_price, gid_sel))
                        st.success("Updated")
                    except Exception as e:
                        st.error(f"Error: {e}")

# -------- Purchases --------
with tab3:
    st.subheader("Record Purchase")
    paddy_df = df_read("SELECT paddy_id, paddy_name FROM paddy_types ORDER BY paddy_name")
    c1, c2, c3 = st.columns(3)
    dt = c1.date_input("Date", value=date.today())
    paddy_sel = c2.selectbox("Paddy Type", options=paddy_df["paddy_id"], format_func=lambda x: paddy_df.set_index("paddy_id").loc[x,"paddy_name"] if not paddy_df.empty else x)
    rate = c3.number_input("Rate (₹/qtl)", min_value=0.0, step=50.0)
    c4, c5, c6 = st.columns(3)
    qty_qtl = c4.number_input("Qty IN (qtl)", min_value=0.0, step=0.1)
    qty_kg = c5.number_input("Qty IN (kg)", min_value=0.0, step=10.0)
    notes = c6.text_input("Notes")
    if st.button("Add Purchase"):
        final_qtl = qty_qtl if qty_qtl>0 else (qty_kg/float(get_cfg("kg_per_qtl", KG_PER_QTL_DEFAULT)) if qty_kg>0 else 0)
        cost = final_qtl * rate if (final_qtl and rate) else 0
        exec_sql("""INSERT INTO purchases(dt,paddy_id,qty_qtl,qty_kg,final_qtl,rate_qtl,cost,notes)
                    VALUES(?,?,?,?,?,?,?,?)""",
                 (dt.isoformat(), paddy_sel, qty_qtl, qty_kg, final_qtl, rate, cost, notes))
        st.success("Saved")

    st.markdown("### Recent Purchases")
    st.dataframe(df_read("""SELECT p.dt as Date, t.paddy_name as Paddy, p.final_qtl as Final_qtl, p.rate_qtl as Rate, p.cost as Cost, p.notes as Notes
                             FROM purchases p LEFT JOIN paddy_types t ON p.paddy_id=t.paddy_id ORDER BY p.id DESC LIMIT 200"""),
                 use_container_width=True)

# -------- Milling Input --------
with tab4:
    st.subheader("Record Milling Input")
    paddy_df = df_read("SELECT paddy_id, paddy_name FROM paddy_types ORDER BY paddy_name")
    c1, c2, c3 = st.columns(3)
    dt = c1.date_input("Date ", value=date.today(), key="mi_date")
    paddy_sel = c2.selectbox("Paddy Type ", options=paddy_df["paddy_id"], format_func=lambda x: paddy_df.set_index("paddy_id").loc[x,"paddy_name"] if not paddy_df.empty else x, key="mi_paddy")
    expense = c3.number_input("Milling Expense (₹)", min_value=0.0, step=100.0)
    c4, c5, c6 = st.columns(3)
    used_qtl = c4.number_input("Paddy Used (qtl)", min_value=0.0, step=0.1)
    used_kg = c5.number_input("Paddy Used (kg)", min_value=0.0, step=10.0)
    notes = c6.text_input("Notes ", key="mi_notes")
    c7, c8 = st.columns(2)
    husk = c7.number_input("Husk Out (qtl)", min_value=0.0, step=0.1)
    polish = c8.number_input("Polish Out (qtl)", min_value=0.0, step=0.1)
    if st.button("Add Milling Input"):
        final_used_qtl = used_qtl if used_qtl>0 else (used_kg/float(get_cfg("kg_per_qtl", KG_PER_QTL_DEFAULT)) if used_kg>0 else 0)
        exec_sql("""INSERT INTO milling_input(dt,paddy_id,used_qtl,used_kg,final_used_qtl,husk_qtl,polish_qtl,expense,notes)
                    VALUES(?,?,?,?,?,?,?,?,?)""",
                 (dt.isoformat(), paddy_sel, used_qtl, used_kg, final_used_qtl, husk, polish, expense, notes))
        st.success("Saved")

    st.markdown("### Recent Milling Inputs")
    st.dataframe(df_read("""SELECT mi.dt as Date, t.paddy_name as Paddy, mi.final_used_qtl as Used_qtl, mi.husk_qtl as Husk, mi.polish_qtl as Polish, mi.expense as Expense
                             FROM milling_input mi LEFT JOIN paddy_types t ON mi.paddy_id=t.paddy_id ORDER BY mi.id DESC LIMIT 200"""),
                 use_container_width=True)

# -------- Milling Output --------
with tab5:
    st.subheader("Record Milling Output (ANY Paddy x ANY Grade)")
    paddy_df = df_read("SELECT paddy_id, paddy_name FROM paddy_types ORDER BY paddy_name")
    grade_df = df_read("SELECT grade_id, grade_name, default_price_qtl FROM rice_grades ORDER BY grade_name")
    c1, c2, c3 = st.columns(3)
    dt = c1.date_input("Date  ", value=date.today(), key="mo_date")
    paddy_sel = c2.selectbox("Paddy Type  ", options=paddy_df["paddy_id"], format_func=lambda x: paddy_df.set_index("paddy_id").loc[x,"paddy_name"] if not paddy_df.empty else x)
    grade_sel = c3.selectbox("Rice Grade / Cut", options=grade_df["grade_id"], format_func=lambda x: grade_df.set_index("grade_id").loc[x,"grade_name"] if not grade_df.empty else x)
    c4, c5 = st.columns(2)
    out_qtl = c4.number_input("Rice OUT (qtl)", min_value=0.0, step=0.1)
    out_kg  = c5.number_input("Rice OUT (kg)", min_value=0.0, step=10.0)
    notes = st.text_input("Notes  ", key="mo_notes")
    if st.button("Add Milling Output"):
        final_out_qtl = out_qtl if out_qtl>0 else (out_kg/float(get_cfg("kg_per_qtl", KG_PER_QTL_DEFAULT)) if out_kg>0 else 0)
        exec_sql("""INSERT INTO milling_output(dt,paddy_id,grade_id,out_qtl,out_kg,final_out_qtl,notes)
                    VALUES(?,?,?,?,?,?,?)""",
                 (dt.isoformat(), paddy_sel, grade_sel, out_qtl, out_kg, final_out_qtl, notes))
        st.success("Saved")

    st.markdown("### Recent Milling Outputs")
    st.dataframe(df_read("""SELECT mo.dt as Date, t.paddy_name as Paddy, g.grade_name as Grade, mo.final_out_qtl as Out_qtl, mo.notes as Notes
                             FROM milling_output mo
                             LEFT JOIN paddy_types t ON mo.paddy_id=t.paddy_id
                             LEFT JOIN rice_grades g ON mo.grade_id=g.grade_id
                             ORDER BY mo.id DESC LIMIT 200"""),
                 use_container_width=True)

# -------- Sales --------
with tab6:
    st.subheader("Record Sales")
    grade_df = df_read("SELECT grade_id, grade_name, default_price_qtl FROM rice_grades ORDER BY grade_name")
    c1, c2, c3 = st.columns(3)
    dt = c1.date_input("Date   ", value=date.today(), key="sa_date")
    product = c2.selectbox("Product", options=["Rice","Husk","Polish"])
    grade_sel = c3.selectbox("Rice Grade (if Rice)", options=[""] + grade_df["grade_id"].tolist(), index=0, format_func=lambda x: (grade_df.set_index("grade_id").loc[x,"grade_name"] if x and not grade_df.empty else ""))
    c4, c5, c6 = st.columns(3)
    qty_qtl = c4.number_input("Qty OUT (qtl)", min_value=0.0, step=0.1)
    qty_kg  = c5.number_input("Qty OUT (kg)", min_value=0.0, step=10.0)
    default_rate = 0.0
    if product=="Rice" and grade_sel:
        try:
            default_rate = float(grade_df.set_index("grade_id").loc[grade_sel,"default_price_qtl"] or 0.0)
        except:
            default_rate = 0.0
    rate = c6.number_input("Rate (₹/qtl)", min_value=0.0, step=50.0, value=default_rate)
    notes = st.text_input("Notes    ", key="sa_notes")
    if st.button("Add Sale"):
        final_qtl = qty_qtl if qty_qtl>0 else (qty_kg/float(get_cfg("kg_per_qtl", KG_PER_QTL_DEFAULT)) if qty_kg>0 else 0)
        revenue = final_qtl * rate if (final_qtl and rate) else 0
        exec_sql("""INSERT INTO sales(dt,product,grade_id,qty_qtl,qty_kg,final_qtl,rate_qtl,revenue,notes)
                    VALUES(?,?,?,?,?,?,?,?,?)""",
                 (dt.isoformat(), product, grade_sel if product=="Rice" else None,
                  qty_qtl, qty_kg, final_qtl, rate, revenue, notes))
        st.success("Saved")

    st.markdown("### Recent Sales")
    st.dataframe(df_read("""SELECT s.dt as Date, s.product as Product, g.grade_name as Grade, s.final_qtl as Qty_qtl, s.rate_qtl as Rate, s.revenue as Revenue, s.notes as Notes
                             FROM sales s LEFT JOIN rice_grades g ON s.grade_id=g.grade_id
                             ORDER BY s.id DESC LIMIT 200"""),
                 use_container_width=True)

# -------- Export / Import --------
st.sidebar.markdown("---")
st.sidebar.subheader("Export / Import")
if st.sidebar.button("Export to Excel (.xlsx)"):
    # Build multi-sheet Excel in memory
    with get_conn() as conn:
        xls = io.BytesIO()
        with pd.ExcelWriter(xls, engine="xlsxwriter") as writer:
            pd.read_sql_query("SELECT * FROM paddy_types", conn).to_excel(writer, sheet_name="Master_PaddyTypes", index=False)
            pd.read_sql_query("SELECT * FROM rice_grades", conn).to_excel(writer, sheet_name="Master_RiceGrades", index=False)
            pd.read_sql_query("SELECT * FROM purchases", conn).to_excel(writer, sheet_name="Purchases", index=False)
            pd.read_sql_query("SELECT * FROM milling_input", conn).to_excel(writer, sheet_name="Milling_Input", index=False)
            pd.read_sql_query("SELECT * FROM milling_output", conn).to_excel(writer, sheet_name="Milling_Output", index=False)
            pd.read_sql_query("SELECT * FROM sales", conn).to_excel(writer, sheet_name="Sales", index=False)
        st.sidebar.download_button("Download data.xlsx", xls.getvalue(), file_name="RRM_Mill_Data.xlsx")

st.sidebar.caption("Tip: Deploy this app on Streamlit Cloud or a small VPS. The SQLite DB file (rrm_tracker.db) stays on the server for persistence.")
